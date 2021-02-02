
import os
import json
import logging
import subprocess
from collections import OrderedDict

from rez.config import config
from rez.package_maker import PackageMaker
from rez.packages import iter_package_families
from rez.utils.formatting import PackageRequest
from rez.resolved_context import ResolvedContext
from rez.developer_package import DeveloperPackage
from rez.utils.logging_ import logger as rez_logger
from rez.packages import get_latest_package_from_string
from rez.package_repository import package_repository_manager

from . import git


DEFAULT_MEMORY_PATH = "memory@any"
BIND_PACKAGES = [
    "os",
    "arch",
    "platform",
]


# silencing rez logger, e.g. on package preprocessing
rez_logger.setLevel(logging.WARNING)


class DevPkgRepository(object):

    def __init__(self, root, memory_path=None):
        src_dev_dirs = [
            os.path.join(root, "packages"),
            os.path.join(root, "downloads"),
        ]

        ext_pkg_list = os.path.join(root, "ext-packages.json")
        if os.path.isfile(ext_pkg_list):
            with open(ext_pkg_list, "r") as ext_f:
                ext_pkg_repos = json.load(ext_f)

            if not isinstance(ext_pkg_repos, list):
                raise TypeError("'ext-packages.json' should be containing a "
                                "list of repositories.")

        else:
            ext_pkg_repos = []

        self._root = root
        self._src_dev_dirs = src_dev_dirs
        self._ext_pkg_repos = ext_pkg_repos
        self._memory = memory_path or DEFAULT_MEMORY_PATH
        self._release = False

    # def set_release(self, release):
    #     self._release = release

    def __contains__(self, pkg):
        return "@".join(pkg.parent.repository.uid) == self._memory

    def load(self):
        """Load developer packages into Rez memory repository

        By making packages from developer packages, and saving them into Rez's
        memory repository, we can then resolve requests to see if any package
        is resolved from memory, and deployed it.

        """
        self._update_ext_packages()

        # for name in BIND_PACKAGES:
        #     self._bind(name)

        packages = dict()
        dev_dirs = self._src_dev_dirs

        # Append `dev_dirs` into `config.packages_path` so the requires can be
        # expanded properly with other pre-installed packages. If we don't do
        # this, requirements like "os-*" or "python-2.*" may raise error like
        # schema validation fail (which is also confusing) due to package not
        # found.
        config.override("packages_path", config.packages_path[:] + dev_dirs)
        # Ensure unversioned package is allowed, so we can iter dev packages.
        config.override("allow_unversioned_packages", True)

        for family in iter_package_families(paths=dev_dirs):
            name = family.name  # package dir name
            versions = dict()

            for _pkg in family.iter_packages():
                data = _pkg.data.copy()
                name = data["name"]  # real name in package.py

                if data.get("github_repo"):
                    repo = data["github_repo"]
                    # get latest release, and mark unavailable if None.
                    result = next(git.get_releases(repo, latest=True))
                    if result:
                        os.environ["GITHUB_REZ_PKG_PAYLOAD_VER"] = result[0]

                maker = PackageMaker(name,
                                     data=data,
                                     package_cls=DeveloperPackage)
                package = maker.get_package()
                data = package.data.copy()

                # preprocessing
                result = package._get_preprocessed(data)
                if result:
                    package, data = result

                data["_uri"] = _pkg.uri
                version = data.get("version", "unversioned")
                versions[version] = data

            packages[name] = versions

        # save collected dev packages in memory repository
        memory_repo = package_repository_manager.get_repository(self._memory)
        memory_repo.data = packages

        config.remove_override("packages_path")
        config.remove_override("allow_unversioned_packages")

    def dependencies(self, name):
        """"""
        is_installed = False
        to_install = OrderedDict()
        package_paths = self._packages_path() + [self._memory]

        pkg_to_deploy = get_latest_package_from_string(name,
                                                       paths=package_paths)
        if pkg_to_deploy is None:
            uri = None
            variants = []  # dev package might not exists
        else:
            name = pkg_to_deploy.qualified_name
            variants = pkg_to_deploy.iter_variants()
            # TODO: check all variants are installed

            if self._is_in_memory(pkg_to_deploy):
                uri = pkg_to_deploy.data["_uri"]
            else:
                uri = pkg_to_deploy.uri
                is_installed = True

        for variant in variants:
            context = self._get_build_context(variant, package_paths)
            for package in context.resolved_packages:
                dep_name = package.qualified_package_name

                if self._is_in_memory(package):
                    # need install
                    to_install.update(self.dependencies(dep_name))

                else:
                    # already installed
                    pass

        if not is_installed:
            to_install[name] = uri

        return to_install

    def deploy(self, dependencies):
        install_path = self._install_path()
        package_paths = self._packages_path() + [self._memory]

        for q_name, _uri in dependencies.items():
            if q_name.startswith("rez-"):
                clear_repo_cache(install_path)
                self._install_rez_as_package(package_paths)
                continue

            args = self._install_cmd()
            subprocess.check_call(args, cwd=os.path.dirname(_uri))

    def _update_ext_packages(self):
        for repo in self._ext_pkg_repos:
            # TODO: checkout latest
            git.clone(
                url=repo["url"],
                dst=os.path.join(self._root, "downloads", repo["name"]),
                branch=repo.get("branch"),
            )

    def _bind(self, name):
        install_path = self._install_path()
        packages_path = self._packages_path()
        pkg = get_latest_package_from_string(name, paths=packages_path)
        if pkg is None:
            subprocess.check_call(self._bind_cmd() + [name])
            clear_repo_cache(install_path)

    def _packages_path(self):
        if self._release:
            return config.nonlocal_packages_path[:]
        else:
            return config.packages_path[:]

    def _install_path(self):
        if self._release:
            return config.release_packages_path
        else:
            return config.local_packages_path

    def _install_cmd(self):
        if self._release:
            return ["rez-release"]
        else:
            return ["rez-build", "--install"]

    def _bind_cmd(self):
        if self._release:
            return ["rez-bind", "--release"]
        else:
            return ["rez-bind"]

    def _get_build_context(self, variant, package_paths):
        implicit_pkgs = list(map(PackageRequest, config.implicit_packages))
        pkg_requests = variant.get_requires(build_requires=True,
                                            private_build_requires=True)
        return ResolvedContext(pkg_requests + implicit_pkgs,
                               building=True,
                               package_paths=package_paths)

    def _is_in_memory(self, pkg):
        return pkg.parent.repository.name() == "memory"

    def _install_rez_as_package(self, package_paths):
        """Use Rez's install script to deploy rez as package
        """
        from rez.packages import get_latest_package_from_string

        rez_install = os.path.join(os.path.abspath(REZ_SRC), "install.py")
        dev_pkg = get_latest_package_from_string("rez", paths=[self._memory])
        dst = self._install_path()

        print("Installing Rez as package..")

        for variant in dev_pkg.iter_variants():
            print("Variant: ", variant)

            context = self._get_build_context(variant, package_paths)
            context.execute_shell(
                command=["python", rez_install, "-v", "-p", dst],
                block=True,
                cwd=REZ_SRC,
            )


def clear_repo_cache(path):
    """Clear filesystem repo family cache after pkg bind/install

    Current use case: Clear cache after rez-bind and before iter dev
    packages into memory. Without this, variants like os-* may not be
    expanded due to filesystem repo doesn't know 'os' has been bind since
    the family list is cached in this session.

    """
    fs_repo = package_repository_manager.get_repository(path)
    fs_repo.get_family.cache_clear()


class PackageInstaller(object):

    def process(self, request):
        pass

    def bind(self, name):
        pass


class PackageReleaser(object):
    pass
