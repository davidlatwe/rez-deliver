
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

    def __init__(self, root, local_dir=None, remote_dir=None, externals=None):
        local_dir = local_dir or "packages"
        remote_dir = remote_dir or "downloads"
        externals = externals or "ext-packages.json"

        dev_package_paths = [
            os.path.join(root, local_dir),
            os.path.join(root, remote_dir),
        ]

        self._root = root
        self._local_dir = local_dir
        self._remote_dir = remote_dir
        self._externals = externals
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
        ext_pkg_list = os.path.join(self._root, self._externals)
        if os.path.isfile(ext_pkg_list):
            with open(ext_pkg_list, "r") as ext_f:
                ext_pkg_repos = json.load(ext_f)
        else:
            ext_pkg_repos = []

        for repo in ext_pkg_repos:
            # TODO: checkout latest
            git.clone(
                url=repo["url"],
                dst=os.path.join(self._root, self._remote_dir, repo["name"]),
                branch=repo.get("branch"),
            )

    def uri(self):
        return self._memory

    def iter_bind_packages(self):
        for name, maker in self.binds.items():
            data = maker().data.copy()
            data["_uri"] = "_bind_"
            yield name, {data["version"]: data}

    def iter_dev_packages(self):
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

                for _pkg in family.iter_packages():
                    data = _pkg.data.copy()
                    name = data["name"]  # real name in package.py

                    if data.get("github_repo"):
                        repo = data["github_repo"]
                        # get latest release, and mark unavailable if None.
                        result = next(git.get_releases(repo, latest=True))
                        if result:
                            os.environ["GITHUB_REZ_PKG_PAYLOAD_VER"] = result[0]

                    package = make_package(name, data=data)
                    data = package.data.copy()

                    # preprocessing
                    result = package._get_preprocessed(data)
                    if result:
                        package, data = result

                    data["_uri"] = _pkg.uri
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


class PackageInstaller(object):

    def __init__(self, dev_repo, rezsrc_path, release):
        self.release = release
        self.dev_repo = dev_repo
        self.rezsrc_path = rezsrc_path
        self._install_list = OrderedDict()

    def run(self, requests, dryrun=False):
        self._install_list.clear()

        for request in requests:
            self._install_list.update(self.dependencies(request))

        if dryrun:
            return

        for q_name, _uri in self._install_list.items():
            name = q_name.split("-", 1)[0]

            if name == "rez":
                self._install_rez_as_package()
                continue

            if name in self.dev_repo.binds:
                self._bind(name)
                continue

            self._build(q_name, cwd=os.path.dirname(_uri))

    def dependencies(self, name):
        """"""
        is_installed = False
        to_install = OrderedDict()

        def installed(pkg):
            return pkg not in self.dev_repo

        pkg_to_deploy = self._get_pkg_from_str(name)

        # TODO: check all variants are installed
        #   By comparing variants of dev package and installed one
        # dev_pkg = self._get_pkg_from_str_in_dev(name)

        if pkg_to_deploy is None:
            uri = None
            variants = []  # dev package might not exists
        else:
            name = pkg_to_deploy.qualified_name
            variants = pkg_to_deploy.iter_variants()

            if installed(pkg_to_deploy):
                uri = pkg_to_deploy.uri
                is_installed = True
            else:
                uri = pkg_to_deploy.data["_uri"]

        for variant in variants:
            context = self._get_build_context(variant)
            for package in context.resolved_packages:
                dep_name = package.qualified_package_name

                if installed(package):
                    pass
                else:
                    to_install.update(self.dependencies(dep_name))

        if not is_installed:
            to_install[name] = uri

        return to_install

    def _install_rez_as_package(self):
        """Use Rez's install script to deploy rez as package
        """
        rezsrc = self.rezsrc_path
        install_path = self._install_path()

        rez_install = os.path.join(os.path.abspath(rezsrc), "install.py")
        dev_pkg = self._get_pkg_from_str_in_dev("rez")

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

    def _get_pkg_from_str(self, name, include_dev=True):
        paths = self._package_paths()
        if include_dev:
            paths += [self.dev_repo.uri()]
        return get_latest_package_from_string(name, paths=paths)

    def _get_pkg_from_str_in_dev(self, name):
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
        pkg = self._get_pkg_from_str(name, include_dev=False)
        if pkg is not None:
            # installed
            return

        if self.release:
            subprocess.check_call(["rez-bind", "--release", name])
        else:
            subprocess.check_call(["rez-bind", name])

        clear_repo_cache(self._install_path())

    def _build(self, name, variant=None, cwd=None):
        pkg = self._get_pkg_from_str(name, include_dev=False)
        if pkg is not None:
            # installed
            return

        if self.release:
            subprocess.check_call(["rez-release"], cwd=cwd)
        else:
            subprocess.check_call(["rez-build", "--install"], cwd=cwd)

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
