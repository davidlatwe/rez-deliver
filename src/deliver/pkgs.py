
import os
import json
import logging
import subprocess
import contextlib
from collections import OrderedDict
from itertools import chain

from rez.config import config
from rez.system import system
from rez.package_maker import PackageMaker
from rez.vendor.version.version import Version
from rez.packages import iter_package_families
from rez.exceptions import PackageNotFoundError
from rez.utils.formatting import PackageRequest
from rez.resolved_context import ResolvedContext
from rez.developer_package import DeveloperPackage
from rez.utils.logging_ import logger as rez_logger
from rez.packages import get_latest_package_from_string
from rez.package_repository import package_repository_manager

from . import git


# silencing rez logger, e.g. on package preprocessing
rez_logger.setLevel(logging.WARNING)


class DevPkgRepository(object):

    LocalDirName = "packages"
    RemoteDirName = "downloads"
    ExternalsName = "ext-packages.json"

    def __init__(self, root=None):

        dev_package_paths = [
            os.path.join(root, self.LocalDirName),
            os.path.join(root, self.RemoteDirName),
        ]

        self._root = root
        self._memory = "memory@" + root
        self._dev_package_paths = dev_package_paths

    @property
    def binds(self):
        return {
            "os": pkg_os,
            "arch": pkg_arch,
            "platform": pkg_platform,
        }

    def __contains__(self, pkg):
        return "@".join(pkg.parent.repository.uid[:2]) == self._memory

    def _update_ext_packages(self):
        ext_pkg_list = os.path.join(self._root, self.ExternalsName)
        if os.path.isfile(ext_pkg_list):
            with open(ext_pkg_list, "r") as ext_f:
                ext_pkg_repos = json.load(ext_f)
        else:
            ext_pkg_repos = []

        for repo in ext_pkg_repos:
            # TODO: checkout latest
            git.clone(
                url=repo["url"],
                dst=os.path.join(self._root, self.RemoteDirName, repo["name"]),
                branch=repo.get("branch"),
            )

    def uri(self):
        return self._memory

    def iter_bind_packages(self):
        for name, maker in self.binds.items():
            data = maker().data.copy()
            data["_dev_src_"] = "_bind_"
            yield name, {data["version"]: data}

    def iter_dev_packages(self):

        def iter_packages_with_version_expand(fam):
            for p in fam.iter_packages():
                github_repo = p.data.get("github_repo")
                if github_repo:
                    for ver_tag in git.get_released_tags(github_repo):
                        os.environ["GITHUB_REZ_PKG_PAYLOAD_VER"] = ver_tag
                        yield p
                else:
                    yield p

        #
        # update external packages, by git-clone or checkout latest
        self._update_ext_packages()

        bind_path = self._memory + "+b"
        dev_paths = self._dev_package_paths + [bind_path]
        with override_config({
            # Append `dev_paths` into `config.packages_path` so the requires
            # can be expanded properly with other pre-installed packages.
            # If we don't do this, requirements like "os-*" or "python-2.*"
            # may raise error like schema validation fail (which is also
            # confusing) due to package not found.
            "packages_path": config.packages_path[:] + dev_paths,
            # Ensure unversioned package is allowed, so we can iter dev
            # packages.
            "allow_unversioned_packages": True,
        }):
            for family in iter_package_families(paths=dev_paths):
                name = family.name  # package dir name
                versions = dict()

                for _pkg in iter_packages_with_version_expand(family):
                    data = _pkg.data.copy()
                    name = data["name"]  # real name in package.py

                    package = make_package(name, data=data)
                    data = package.data.copy()

                    # preprocessing
                    result = package._get_preprocessed(data)
                    if result:
                        package, data = result

                    data["_dev_src_"] = _pkg.uri
                    version = data.get("version", "unversioned")
                    versions[version] = data

                yield name, versions

    def reload(self):
        """Load developer packages into Rez memory repository

        By making packages from developer packages, and saving them into Rez's
        memory repository, we can then resolve requests to see if any package
        is resolved from memory, and deployed it.

        """
        b = package_repository_manager.get_repository(self._memory + "+b")
        b.data = {
            name: versions for name, versions
            in self.iter_bind_packages()
        }
        mem_repo = package_repository_manager.get_repository(self._memory)
        mem_repo.data = {
            name: versions for name, versions
            in chain(self.iter_bind_packages(), self.iter_dev_packages())
        }

    def update(self, name, version, data):
        mem_repo = package_repository_manager.get_repository(self._memory)
        if name in mem_repo.data:
            mem_repo.data[name][version] = data
        else:
            mem_repo.data[name] = {version: data}


class PackageInstaller(object):

    def __init__(self, dev_repo, rezsrc_path, release):
        self.release = release
        self.dev_repo = dev_repo
        self.rezsrc_path = rezsrc_path
        self._requirements = OrderedDict()

    def reset(self):
        self._requirements.clear()

    def manifest(self):
        return self._requirements.copy()

    def run(self):
        for (q_name, v_index), (exists, src) in self._requirements.items():
            if exists:
                continue

            name = q_name.split("-", 1)[0]

            if name == "rez":
                self._install_rez_as_package()
                continue

            if name in self.dev_repo.binds:
                self._bind(name)
                continue

            self._build(os.path.dirname(src), variant=v_index)

    def resolve(self, request, variant_index=None):
        """"""
        develop = self._get_develop_pkg_from_str(request)
        package = self._get_installed_pkg_from_str(request)

        if develop is None and package is None:
            raise PackageNotFoundError("%s not found in develop repository "
                                       "nor in installed package paths."
                                       % request)
        if develop is None:
            name = package.qualified_name
            variants = package.iter_variants()
            source = package.uri
        else:
            name = develop.qualified_name
            variants = develop.iter_variants()
            source = develop.data["_dev_src_"]

        if package is None:
            pkg_variants_req = []
        else:
            pkg_variants_req = [v.variant_requires
                                for v in package.iter_variants()]

        for variant in variants:
            if variant_index is not None and variant_index != variant.index:
                continue

            exists = variant.variant_requires in pkg_variants_req

            context = self._get_build_context(variant)
            for pkg in context.resolved_packages:
                self.resolve(request=pkg.qualified_package_name,
                             variant_index=pkg.index)

            self._requirements[(name, variant.index)] = (exists, source)

    def _install_rez_as_package(self):
        """Use Rez's install script to deploy rez as package
        """
        rezsrc = self.rezsrc_path
        install_path = self._install_path()

        rez_install = os.path.join(os.path.abspath(rezsrc), "install.py")
        dev_pkg = self._get_develop_pkg_from_str("rez")

        print("Installing Rez as package..")

        clear_repo_cache(install_path)

        for variant in dev_pkg.iter_variants():
            print("Variant: ", variant)

            context = self._get_build_context(variant)
            context.execute_shell(
                command=["python", rez_install, "-v", "-p", install_path],
                block=True,
                cwd=rezsrc,
            )

    def _get_installed_pkg_from_str(self, name):
        paths = self._package_paths()
        return get_latest_package_from_string(name, paths=paths)

    def _get_develop_pkg_from_str(self, name):
        paths = [self.dev_repo.uri()]
        return get_latest_package_from_string(name, paths=paths)

    def _get_build_context(self, variant):
        paths = self._package_paths() + [self.dev_repo.uri()]
        implicit_pkgs = list(map(PackageRequest, config.implicit_packages))
        pkg_requests = variant.get_requires(build_requires=True,
                                            private_build_requires=True)
        return ResolvedContext(pkg_requests + implicit_pkgs,
                               building=True,
                               package_paths=paths)

    def _bind(self, name):
        pkg = self._get_installed_pkg_from_str(name)
        if pkg is not None:
            # installed
            return

        if self.release:
            subprocess.check_call(["rez-bind", "--release", name])
        else:
            subprocess.check_call(["rez-bind", name])

        clear_repo_cache(self._install_path())

    def _build(self, path, variant=None):
        variant_cmd = [] if variant is None else ["--variants", str(variant)]

        if self.release:
            args = ["rez-release"] + variant_cmd
            subprocess.check_call(args, cwd=path)
        else:
            args = ["rez-build", "--install"] + variant_cmd
            subprocess.check_call(args, cwd=path)

        clear_repo_cache(self._install_path())

    def _package_paths(self):
        if self.release:
            return config.nonlocal_packages_path[:]
        else:
            return config.packages_path[:]

    def _install_path(self):
        if self.release:
            return config.release_packages_path
        else:
            return config.local_packages_path


@contextlib.contextmanager
def override_config(entries):
    try:
        for key, value in entries.items():
            config.override(key, value)
        yield

    finally:
        for key in entries.keys():
            config.remove_override(key)


def clear_repo_cache(path):
    """Clear filesystem repo family cache after pkg bind/install

    Current use case: Clear cache after rez-bind and before iter dev
    packages into memory. Without this, variants like os-* may not be
    expanded, due to filesystem repo doesn't know 'os' has been bind since
    the family list is cached in this session.

    """
    fs_repo = package_repository_manager.get_repository(path)
    fs_repo.get_family.cache_clear()


def make_package(name, data):
    maker = PackageMaker(name, data=data, package_cls=DeveloperPackage)
    return maker.get_package()


def pkg_os():
    data = {"version": Version(system.os),
            "requires": ["platform-%s" % system.platform,
                         "arch-%s" % system.arch]}
    return make_package("os", data=data)


def pkg_arch():
    data = {"version": Version(system.arch)}
    return make_package("arch", data=data)


def pkg_platform():
    data = {"version": Version(system.platform)}
    return make_package("platform", data=data)
