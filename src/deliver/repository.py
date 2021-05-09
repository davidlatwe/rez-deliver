
import os
import logging
import subprocess

from rez.config import config as rezconfig
from rez.utils.formatting import PackageRequest
from rez.resolved_context import ResolvedContext
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


class PackageLoader(object):
    """Load developer packages from multiple repositories

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

    def __init__(self):
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
    def maker_root(self):
        return self._maker_repo.root

    @property
    def paths(self):
        return [repo.mem_uid for repo in self._dev_repos]

    def get_maker_made_package(self, name):
        paths = [self._maker_repo.mem_uid]
        return get_latest_package_from_string(name, paths=paths)

    def load(self, name=None, dependency=True):
        """Load package and it's dependencies optionally from all repositories

        Args:
            name (str): package family name, optional. Load all if not given.
            dependency (bool): If True and `name` given, load all dependencies
                recursively.

        Returns:
            None

        """
        dev_paths = [repo.root for repo in self._dev_repos[:-1]]
        dev_paths.append(self._maker_repo.mem_uid)
        # Noted that the maker repo doesn't have filesystem based package,
        #   use memory path `mem_uid` as root instead.

        with override_config({
            # Append `dev_paths` into `config.packages_path` so the requires
            # can be expanded properly with other pre-installed packages.
            # If we don't do this, requirements like "os-*" or "python-2.*"
            # may raise error like schema validation fail (which is also
            # confusing) due to package not found.
            "packages_path": rezconfig.packages_path[:] + dev_paths,
            # Ensure unversioned package is allowed, so we can iter dev
            # packages.
            "allow_unversioned_packages": True,
        }):
            for repo in self._dev_repos:
                repo.load(name=name)

        if name and dependency:
            # lazy load, recursively
            requires = []
            for package in self.iter_packages(name):
                # package.set_context(ResolvedContext([]))
                for variant in package.iter_variants():
                    requires += variant.get_requires(
                        build_requires=True,
                        private_build_requires=True
                    )

            seen = set()
            for req in requires:
                if isinstance(req, str):
                    req = PackageRequest(req)
                if req.name not in seen and not req.ephemeral:
                    seen.add(req.name)
                    self.load(name=req.name)

    def find(self, request, load_dependency=False):
        """Find requested latest package

        Args:
            request (PackageRequest): package request object
            load_dependency (bool): If True, the dependency will be loaded
                recursively before returning searched result.

        Returns:
            `Package`: latest package in requested range, None if not found.

        """
        self.load(name=request.name, dependency=load_dependency)
        return get_latest_package(name=request.name,
                                  range_=request.range_,
                                  paths=self.paths)

    def iter_package_families(self):
        for family in iter_package_families(paths=self.paths):
            yield family

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
        self._loaded = set()
        self._all_loaded = False

    def __contains__(self, pkg):
        uid = "@".join(pkg.parent.repository.uid[:2])
        return uid == self.mem_uid

    def _load_build_time_variants(self, package):
        """Re-evaluate package variants as build-time mode

        Package should be re-evaluated for each variant as in build so to
        get the correct variant build-requires.

        Args:
            package (`DeveloperPackage`): an instance of DeveloperPackage

        Returns:
            `DeveloperPackage`: the input `package` itself

        """
        # TODO: convert @early into @late for varianted attributes, and drop
        #   'buildtime' repository
        resources = list()

        for variant in package.iter_variants():
            index = variant.index

            re_evaluated_package = package.get_reevaluated({
                "building": True,
                "build_variant_index": index or 0,
                "build_variant_requires": variant.variant_requires
            })
            re_evaluated_variant = re_evaluated_package.get_variant(index)
            # noted that here is the resource object being collected
            resources.append(re_evaluated_variant.resource)

        if resources:
            # Here we preserve each re-evaluated variant's resource object,
            # see `deliver.rezplugins.package_repository.buildtime` for how
            # they will be retrieved.
            package.data["_build_time_variant_resources"] = resources

        return package

    @property
    def mem_uid(self):
        # noted that here we use the `buildtime` memory repository plugin
        # to preserve loaded developer packages.
        return "buildtime@" + self._root

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

    def load(self, name=None):
        """Load dev-packages into build-time memory repository

        Args:
            name (str): package family name, optional.
                All packages will be loaded if family name not given.

        Returns:
            None

        """
        if self._all_loaded:
            return

        if name:
            # lazy load
            if name in self._loaded:
                return

            for version, data in self.get_dev_package_versions(name):
                if name not in self.mem_repo.data:
                    self.mem_repo.data[name] = dict()
                self.mem_repo.data[name][version] = data

            self._loaded.add(name)

        else:
            # full load
            self.mem_repo.data = {
                name: versions for name, versions
                in self.iter_dev_packages()
            }

            self._all_loaded = True


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

    def iter_dev_packages(self):
        for name in self.makers:
            package = self._make_package(name)
            data = package.data
            yield name, {data["version"]: data}

    def get_dev_package_versions(self, name):
        package = self._make_package(name)
        if package:
            data = package.data
            version = data.get("version", "_NO_VERSION")

            yield version, data

    def iter_package_family_names(self):
        for name in self.makers:
            yield name

    def _make_package(self, name):
        release = self._loader.release
        func = self.makers.get(name)
        if func is not None:
            maker = func(release=release)
            maker.__source__ = self.root
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

    def iter_dev_packages(self):
        for family in iter_package_families(paths=[self._root]):
            name = family.name  # package dir name
            versions = dict()

            for version, data in self._generate_dev_packages(family):
                versions[version] = data

            yield name, versions

    def get_dev_package_versions(self, name):
        it = iter_package_families(paths=[self._root])
        family = next((f for f in it if f.name == name), None)
        if family is None:
            return

        for version, data in self._generate_dev_packages(family):
            yield version, data

    def iter_package_family_names(self):
        for family in iter_package_families(paths=[self._root]):
            yield family.name  # package dir name

    def _generate_dev_packages(self, family):
        for package in family.iter_packages():
            for dev_package in self._load_dev_packages(package):
                data = dev_package.data.copy()
                data["__source__"] = dev_package.filepath
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

    def _load_dev_packages(self, package):
        if not package.uri:  # A sub-dir in Family dir without package file.
            return

        pkg_path = os.path.dirname(package.uri)
        with os_chdir(pkg_path):
            # If we don't change cwd to package dir, dev package may not be
            # evaluated correctly.
            # For example, `git shortlog` is often being used to get package
            # authors, which will not work and hang the process with message
            # "reading log message from standard input", if cwd is not (in)
            # a git repository.
            git_url = package.data.get("git_url")
            if git_url:
                for ver_tag in self._git_tags(git_url):
                    # generate versions from git tags
                    with temp_env("REZ_DELIVER_PKG_PAYLOAD_VER", ver_tag):
                        package = DeveloperPackage.from_path(pkg_path)
                        yield self._load_build_time_variants(package)
            else:
                package = DeveloperPackage.from_path(pkg_path)
                yield self._load_build_time_variants(package)
