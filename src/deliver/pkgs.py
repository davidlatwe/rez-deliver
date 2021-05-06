"""A module that meant to find/resolve/install developer packages

Example:
    # setup rez-deliver config so it could find developer package
    >>> installer = PackageInstaller()
    >>> installer.resolve("foo")
    >>> installer.manifest()
    >>> installer.run()

"""
import os
import logging
import functools
import subprocess
import contextlib

from rez.config import config as rezconfig
from rez.packages import iter_package_families
from rez.utils.formatting import PackageRequest
from rez.resolved_context import ResolvedContext
from rez.developer_package import DeveloperPackage
from rez.utils.logging_ import logger as rez_logger
from rez.packages import get_latest_package_from_string, get_latest_package
from rez.package_repository import package_repository_manager
from rez.exceptions import PackageFamilyNotFoundError, PackageNotFoundError

from deliver.maker.os import pkg_os
from deliver.maker.arch import pkg_arch
from deliver.maker.platform import pkg_platform
from deliver.maker.rez import pkg_rez


# silencing rez logger, e.g. on package preprocessing
rez_logger.setLevel(logging.WARNING)


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

    def iter_package_names(self):
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

    def iter_package_names(self):
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

    def iter_package_names(self):
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
            for repo in self._dev_repos:
                versions = repo.mem_repo.data.get(name, dict())
                for version, data in versions.items():
                    requires += data.get("requires", [])
                    requires += data.get("build_requires", [])
                    requires += data.get("private_build_requires", [])
                    for variant in data.get("variants", []):
                        requires += variant
            seen = set()
            for req_str in requires:
                req = PackageRequest(req_str)
                if req.name not in seen and not req.ephemeral:
                    seen.add(req.name)
                    self.load(name=req.name)

    def find(self, request, load_dependency=False):
        """Find requested latest package

        Args:
            request (str): package request string
            load_dependency (bool): If True, the dependency will be loaded
                recursively before returning searched result.

        Returns:
            `Package`: latest package in requested range, None if not found.

        """
        request = PackageRequest(request)
        self.load(name=request.name, dependency=load_dependency)
        return get_latest_package(name=request.name,
                                  range_=request.range_,
                                  paths=self.paths)

    def iter_package_families(self):
        for family in iter_package_families(paths=self.paths):
            yield family

    def iter_package_names(self):
        seen = set()
        for repo in self._dev_repos:
            for name in repo.iter_package_names():
                if name not in seen:
                    yield name
                seen.add(name)


class Required(object):
    __slots__ = ("name", "index", "source", "status", "depended")

    def __init__(self, name, index):
        self.name = name
        self.index = index
        self.source = None
        self.status = None
        self.depended = []

    @classmethod
    def get(cls, name, index=-1, from_=None):
        from_ = from_ or []
        try:
            req_id = from_.index((name, index))
        except ValueError:
            return cls(name, index)
        else:
            return from_[req_id]

    def __eq__(self, other):
        return other == (self.name, self.index)

    def __repr__(self):
        return "Required(name='%s', index=%r, status=%s)" \
               % (self.name,
                  self.index,
                  PackageInstaller.StatusMapStr[self.status])


class RequestSolver(object):

    Ready = 1
    Installed = 2
    External = 3
    ResolveFailed = 4
    PackageNotFound = 5

    StatusMapStr = {
        Ready: "ready",
        Installed: "installed",
        External: "external",
        ResolveFailed: "failed",
        PackageNotFound: "missing",
    }

    def __init__(self, loader):
        self.loader = loader or PackageLoader()
        self._requirements = list()
        self._implicits = list()  # TODO: Implement version picking
        self._conflicts = list()
        self.__depended = None

    @property
    def installed_packages_path(self):
        return rezconfig.packages_path

    def reset(self):
        self._requirements = []
        self.__depended = None

    def manifest(self):
        return self._requirements[:]

    def find_installed(self, name):
        paths = self.installed_packages_path
        return get_latest_package_from_string(name, paths=paths)

    def zip_longest_variants(self, this, that):
        r = (lambda requires: " ".join(str(_) for _ in requires))

        this_vans_ = list(this.iter_variants()) if this else []
        that_vans_ = {
            r(v.variant_requires): v for v in that.iter_variants()
        } if that else dict()

        longest = max(len(this_vans_), len(that_vans_))
        for i in range(longest):
            if this_vans_ and that_vans_:
                this_van = this_vans_.pop(0)
                that_van = that_vans_.pop(r(this_van.variant_requires), None)

            elif this_vans_ and not that_vans_:
                this_van = this_vans_.pop(0)
                that_van = None

            elif not this_vans_ and that_vans_:
                this_van = None
                _, that_van = that_vans_.popitem()

            else:
                return

            yield this_van, that_van

    def resolve(self, request, variant_index=None):
        """Resolve request and it's dependencies recursively

        Call `manifest()` to show resolved requirements.

        Args:
            request (str): Package request string
            variant_index (int): Variant index, optional.

        Returns:
            None

        """
        # find latest package in requested range
        developer = self.loader.find(request, load_dependency=True)
        installed = self.find_installed(request)

        if developer is None and installed is None:
            # package not found
            requested = Required.get(request, from_=self._requirements)
            requested.status = self.PackageNotFound
            self._append(requested)

            return

        status = None

        if developer and installed:
            # prefer dev package if version is different
            if developer.version > installed.version:
                installed = None
                status = self.Ready
            elif developer.version < installed.version:
                developer = None
                status = self.Installed
            else:
                # same version, keep both
                status = self.Ready

        if developer:
            name = developer.qualified_name
            source = developer.data["__source__"]
            status = status or self.Ready
        else:
            name = installed.qualified_name
            source = installed.uri
            status = status or self.External

        # Only if developer and installed package have same version, they
        #   both get kept and iterated together. The reason for this is
        #   because installed package may have different variant sets than
        #   the developer one, even they are same version. Not likely, but
        #   could happen.
        for d_van, i_van in self.zip_longest_variants(developer, installed):
            variant = i_van or d_van
            if variant_index is not None and variant_index != variant.index:
                continue

            if status == self.Ready and variant is i_van:
                status = self.Installed

            requested = Required.get(name, variant.index)
            requested.source = source
            requested.status = status

            if self.__depended:
                requested.depended.append(self.__depended)

            # resolve variant's requirement
            variant_requires = variant.get_requires(
                build_requires=True,
                private_build_requires=True
            )
            try:
                context = self._build_context(variant_requires)
            except (PackageFamilyNotFoundError, PackageNotFoundError) as e:
                print(e)
                requested.status = self.ResolveFailed

            else:
                if not context.success:
                    context.print_info()
                    requested.status = self.ResolveFailed
                else:
                    for pkg in context.resolved_packages:
                        request_id = (pkg.qualified_package_name, pkg.index)
                        if request_id in self._requirements:
                            continue
                        self.__depended = requested
                        self.resolve(request=pkg.qualified_package_name,
                                     variant_index=pkg.index)
            self._append(requested)
        self.__depended = None  # reset

    def _build_context(self, variant_requires):
        paths = self.installed_packages_path + self.loader.paths
        requests = variant_requires + self._implicits + self._conflicts
        return ResolvedContext(requests, building=True, package_paths=paths)

    def _append(self, requested):
        if requested not in self._requirements:
            self._requirements.append(requested)


class PackageInstaller(RequestSolver):

    def __init__(self, loader=None):
        super(PackageInstaller, self).__init__(loader=loader)
        self.release = False

    @property
    def installed_packages_path(self):
        c, r = rezconfig, self.release
        return c.nonlocal_packages_path if r else c.packages_path

    @property
    def deploy_path(self):
        c, r = rezconfig, self.release
        return c.release_packages_path if r else c.local_packages_path

    def target(self, path):
        """
        Only set to 'release' when the `path` is release_packages_path.
        """
        path = expand_path(path)
        release = path == expand_path(rezconfig.release_packages_path)

        print("Mode: %s" % ("release" if release else "install"))
        self.release = release
        self.loader.release = release
        self.reset()

    def run(self):
        for _ in self.run_iter():
            pass

    def run_iter(self):
        for requested in self._requirements:
            if requested.status != self.Ready:
                # TODO: prompt warning if the status is `ResolveFailed`
                continue

            if requested.source == self.loader.maker_root:
                self._make(requested.name,
                           variant=requested.index)
            else:
                self._build(os.path.dirname(requested.name),
                            variant=requested.index)

            yield requested

    def _make(self, name, variant=None):
        deploy_path = self.deploy_path
        if not os.path.isdir(deploy_path):
            os.makedirs(deploy_path)

        made_pkg = self.loader.get_maker_made_package(name)
        made_pkg.__install__(deploy_path, variant)

        clear_repo_cache(deploy_path)

    def _build(self, src_dir, variant=None):
        variant_cmd = [] if variant is None else ["--variants", str(variant)]
        deploy_path = self.deploy_path
        env = os.environ.copy()

        if not os.path.isdir(deploy_path):
            os.makedirs(deploy_path)

        if self.release:
            env["REZ_RELEASE_PACKAGES_PATH"] = deploy_path
            args = ["rez-release"] + variant_cmd
            self._run_command(args, cwd=src_dir, env=env)
        else:
            env["REZ_LOCAL_PACKAGES_PATH"] = deploy_path
            args = ["rez-build", "--install"] + variant_cmd
            self._run_command(args, cwd=src_dir)

        clear_repo_cache(deploy_path)

    def _run_command(self, cmd_args, **kwargs):
        print("Running command:\n    %s\n" % cmd_args)
        subprocess.check_call(cmd_args, **kwargs)


@contextlib.contextmanager
def temp_env(key, value):
    try:
        os.environ[key] = value
        yield
    finally:
        if key in os.environ:
            del os.environ[key]


@contextlib.contextmanager
def os_chdir(path):
    cwd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(cwd)


@contextlib.contextmanager
def override_config(entries):
    previous_override = rezconfig.overrides.copy()

    for key, value in entries.items():
        rezconfig.override(key, value)

    yield

    for key in entries.keys():
        rezconfig.remove_override(key)

    for key, value in previous_override.items():
        if key in entries:
            rezconfig.override(key, value)


def clear_repo_cache(path):
    """Clear filesystem repo family cache after pkg bind/install

    Current use case: Clear cache after rez-bind and before iter dev
    packages into memory. Without this, variants like os-* may not be
    expanded, due to filesystem repo doesn't know 'os' has been bind since
    the family list is cached in this session.

    """
    fs_repo = package_repository_manager.get_repository(path)
    fs_repo.get_family.cache_clear()


def expand_path(path):
    path = functools.reduce(
        lambda _p, f: f(_p),
        [path,
         os.path.expanduser,
         os.path.expandvars,
         os.path.normpath]
    )

    return path
