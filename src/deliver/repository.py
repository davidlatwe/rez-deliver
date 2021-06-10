
import os
import logging
import subprocess
from functools import wraps

from rez.config import config as rezconfig
from rez.utils.formatting import PackageRequest
from rez.developer_package import DeveloperPackage
from rez.utils.logging_ import logger as rez_logger
from rez.package_repository import package_repository_manager
from rez.packages import (
    iter_package_families,
    iter_packages,
    get_latest_package,
    get_latest_package_from_string,
)

from deliver.lib import expand_path, override_config, temp_env, os_chdir
from deliver.maker.os import pkg_os
from deliver.maker.arch import pkg_arch
from deliver.maker.platform import pkg_platform
from deliver.maker.rez import pkg_rez


# silencing rez logger, e.g. on package preprocessing
rez_logger.setLevel(logging.WARNING)


def _with_loader_config(fn):
    @wraps(fn)
    def decorated(self, *args, **kwargs):
        with override_config(self.settings):
            return fn(self, *args, **kwargs)
    return decorated


def _iter_with_loader_config(fn):
    @wraps(fn)
    def decorated(self, *args, **kwargs):
        with override_config(self.settings):
            for item in fn(self, *args, **kwargs):
                yield item
    return decorated


class PackageLoader(object):
    """A singleton that loads developer packages from multiple repositories

    The loader will look for packages from all registered repository paths in
    rezconfig. For example:

        # rezconfig.py
        plugins = {
            "command": {
                "deliver": {
                    "dev_repository_roots": [
                        "/path/to/yours",
                        "/path/to/shared",
                    ],
        }}}

    """
    __singleton = None
    __initialized = False

    def __new__(cls, *args, **kwargs):
        if cls.__singleton is None:
            cls.__singleton = super().__new__(cls)
        return cls.__singleton

    @classmethod
    def clear_instance(cls):
        cls.__singleton = None
        cls.__initialized = False

    def __init__(self):
        if self.__initialized:
            return
        self.__initialized = True
        # init
        #
        deliverconfig = rezconfig.plugins.command.deliver
        maker_repo = MakePkgRepo(loader=self)
        dev_repos = [
            DevPkgRepo(root=expand_path(root), loader=self)
            for root in deliverconfig.dev_repository_roots
        ]
        dev_repos += [maker_repo]

        self.release = False
        self._dev_repos = dev_repos
        self._maker_repo = maker_repo

    @property
    def settings(self):
        return {
            # Append `dev_paths` into `config.packages_path` so the requires
            # can be expanded properly with other pre-installed packages.
            # If we don't do this, requirements like "os-*" or "python-2.*"
            # may raise error like schema validation fail (which is also
            # confusing) due to package not found.
            "packages_path": rezconfig.packages_path[:] + self.paths,
            # Ensure unversioned package is allowed, so we can iter dev
            # packages.
            "allow_unversioned_packages": True,
        }

    @property
    def maker_source(self):
        return self._maker_repo.mem_uid

    @property
    def paths(self):
        return [repo.mem_uid for repo in self._dev_repos]

    def get_maker_made_package(self, name):
        paths = [self._maker_repo.mem_uid]
        return get_latest_package_from_string(name, paths=paths)

    @_with_loader_config
    def find(self, request):
        """Find requested latest package

        Args:
            request (PackageRequest): package request object

        Returns:
            `Package`: latest package in requested range, None if not found.

        """
        return get_latest_package(name=request.name,
                                  range_=request.range_,
                                  paths=self.paths)

    @_iter_with_loader_config
    def iter_package_families(self):
        for family in iter_package_families(paths=self.paths):
            yield family

    @_iter_with_loader_config
    def iter_packages(self, name, range_=None):
        for package in iter_packages(name, range_=range_, paths=self.paths):
            yield package

    def iter_package_family_names(self):
        seen = set()
        for repo in self._dev_repos:
            for name in repo.iter_package_family_names():
                if name not in seen:
                    yield name
                seen.add(name)


class Repo(object):
    """Base class of developer package repository, internal used."""

    def __init__(self, root, loader):
        """
        Args:
            root: the location of developer package repository
            loader: an instance of `PackageLoader`
        """
        self._root = root
        self._loader = loader

        # mount dev repo instance to memory repository
        self._loaded_cache = dict()
        self.mem_repo.data = self

    @property
    def mem_uid(self):
        return "memory@" + self._root

    @property
    def mem_repo(self):
        return package_repository_manager.get_repository(self.mem_uid)

    @property
    def root(self):
        return self._root

    def iter_dev_packages(self):
        raise NotImplementedError

    def get_dev_package_versions(self, name):
        raise NotImplementedError

    def iter_package_family_names(self):
        raise NotImplementedError

    # Simple dict-like interface for memory repository to read
    #
    def __getitem__(self, name):
        return {k: v for k, v in self.get_dev_package_versions(name)}

    def get(self, key, default=None):
        return self.__getitem__(key) or default

    def keys(self):
        return self.iter_package_family_names()

    def __contains__(self, pkg):
        if isinstance(pkg, str):
            # querying from memory repository
            return self.has_package(pkg)
        else:
            uid = "@".join(pkg.parent.repository.uid[:2])
            return uid == self.mem_uid

    def has_package(self, name):
        raise NotImplementedError


class MakePkgRepo(Repo):
    """A set of pre-defined package-maker generated packages, like rez-bind"""

    def __init__(self, loader):
        Repo.__init__(self, root="rez:package_maker", loader=loader)

    @property
    def makers(self):
        return {
            "os": pkg_os,
            "arch": pkg_arch,
            "platform": pkg_platform,
            "rez": pkg_rez,
        }

    def has_package(self, name):
        return name in self.makers

    def iter_dev_packages(self):
        for name in self.makers:
            if name in self._loaded_cache:
                versions = self._loaded_cache[name]

            else:
                package = self._make_package(name)
                data = package.data
                version = data.get("version", "_NO_VERSION")
                versions = {version: data}
                self._loaded_cache[name] = versions

            yield name, versions

    def get_dev_package_versions(self, name):
        if name in self._loaded_cache:
            versions = self._loaded_cache[name]
            for version, data in versions.items():
                yield version, data

        else:
            package = self._make_package(name)
            if package is None:
                return

            data = package.data
            version = data.get("version", "_NO_VERSION")
            versions = {version: data}

            yield version, data

            self._loaded_cache[name] = versions

    def iter_package_family_names(self):
        for name in self.makers:
            yield name

    def _make_package(self, name):
        release = self._loader.release
        func = self.makers.get(name)
        if func is not None:
            maker = func(release=release)
            maker.__source__ = self.mem_uid
            return maker.get_package()


class DevPkgRepo(Repo):
    """Developer package repository that can work with git tag

    If the developer package has an attribute `git_url` that returns a valid
    git-remote url string, and `git` exists in $PATH, git tags will be fetched
    from remote and generate package per tag into different versions.

    Example:
        # package.py

        git_url = "https://github.com/davidlatwe/delivertest.git"

        @early()
        def version():
            import os

            package_ver = "p1"
            payload_ver = os.getenv("REZ_DELIVER_PKG_PAYLOAD_VER")

            if payload_ver:
                return "%s-%s" % (payload_ver, package_ver)
            else:
                return "0.0.0-" + package_ver

    Note:
        You may want to use this kind of package version specification:

            <package payload version>-<package definition version>

        E.g. `0.1.0-p1`

    """
    def __init__(self, root, loader):
        Repo.__init__(self, root=root, loader=loader)
        self._seen_cache = dict()

    def has_package(self, name):
        existence = self._seen_cache.get(name)
        if existence is None:
            for family in self.iter_package_family_names():
                if name == family:
                    existence = True
                    break
            self._seen_cache[name] = existence or False

        return existence

    def iter_dev_packages(self):
        for family in iter_package_families(paths=[self._root]):
            name = family.name  # package dir name

            if name in self._loaded_cache:
                versions = self._loaded_cache[name]

            else:
                versions = dict()
                for version, data in self._generate_dev_packages(family):
                    versions[version] = data
                self._loaded_cache[name] = versions

            yield name, versions

    def get_dev_package_versions(self, name):
        if name in self._loaded_cache:
            versions = self._loaded_cache[name]
            for version, data in versions.items():
                yield version, data

        else:
            it = iter_package_families(paths=[self._root])
            family = next((f for f in it if f.name == name), None)
            if family is None:
                return

            versions = dict()
            for version, data in self._generate_dev_packages(family):
                versions[version] = data
                yield version, data

            self._loaded_cache[name] = versions

    def iter_package_family_names(self):
        for family in iter_package_families(paths=[self._root]):
            yield family.name  # package dir name

    def _generate_dev_packages(self, family):
        for package in family.iter_packages():  # package order is random
            if not package.uri:  # A sub-dir in Family dir without package file
                continue

            filepath = package.uri
            dirpath = os.path.dirname(filepath)
            with os_chdir(dirpath):
                # If we don't change cwd to package dir, dev package may
                # not be evaluated correctly.
                # For example, `git shortlog` is often being used to get
                # package authors, which will not work and hang the process
                # with message "reading log message from standard input", if
                # cwd is not (in) a git repository.

                git_url = package.data.get("git_url")
                tags = (
                    self._git_tags(git_url) if git_url else ["__no_remote__"]
                )
                for ver_tag in tags:
                    # generate versions from git tags
                    with temp_env("REZ_DELIVER_PKG_PAYLOAD_VER", ver_tag):
                        developer = DeveloperPackage.from_path(dirpath)

                        data = developer.data.copy()
                        data["__source__"] = developer.filepath
                        version = data.get("version", "_NO_VERSION")

                        yield version, data

    def _git_tags(self, url):
        args = ["git", "ls-remote", "--tags", url]
        try:
            output = subprocess.check_output(args, universal_newlines=True)
        except subprocess.CalledProcessError:
            yield "__git_failed__"
        else:
            for line in output.splitlines():
                yield line.split("refs/tags/")[-1]
