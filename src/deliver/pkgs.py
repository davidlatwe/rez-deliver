
import os
import re
import sys
import shutil
import logging
import requests
import functools
import subprocess
import contextlib
from tempfile import mkdtemp
try:
    from importlib.metadata import Distribution
except ImportError:
    from importlib_metadata import Distribution

from rez.config import config as rezconfig
from rez.system import system
from rez.package_maker import PackageMaker, make_package
from rez.packages import iter_package_families
from rez.utils.formatting import PackageRequest
from rez.resolved_context import ResolvedContext
from rez.developer_package import DeveloperPackage
from rez.utils.logging_ import logger as rez_logger
from rez.packages import get_latest_package_from_string, get_latest_package
from rez.package_repository import package_repository_manager
from rez.vendor.version.version import Version, VersionError
from rez.utils.lint_helper import env
from rez.exceptions import PackageNotFoundError


# silencing rez logger, e.g. on package preprocessing
rez_logger.setLevel(logging.WARNING)


def expand_path(path):
    path = functools.reduce(
        lambda _p, f: f(_p),
        [path,
         os.path.expanduser,
         os.path.expandvars,
         os.path.normpath]
    )

    return path


"""
FileSystem Repo(s)  BindPackageRepo
 |                      |
 |                      |
 |         *------------*
 |         |
 V         V
MainMemoryRepo


"""


class Repo(object):

    def __init__(self, root):
        self._root = root

    def __contains__(self, pkg):
        uid = "@".join(pkg.parent.repository.uid[:2])
        return uid == self.mem_uid

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

    def iter_package_names(self):
        raise NotImplementedError

    def load(self, name=None):
        """Load dev-packages into memory repository"""
        if name:
            # lazy load, recursively
            requires = []
            for version, data in self.get_dev_package_versions(name):
                if name not in self.mem_repo.data:
                    self.mem_repo.data[name] = dict()
                self.mem_repo.data[name][version] = data

                requires += data.get("requires", [])
                requires += data.get("build_requires", [])
                requires += data.get("private_build_requires", [])
                for variant in data.get("variants", []):
                    requires += variant

            for req_str in requires:
                req = PackageRequest(req_str)
                if req.ephemeral or req.name in self.mem_repo.data:
                    continue
                self.load(name=req.name)

        else:
            # full load
            self.mem_repo.data = {
                name: versions for name, versions
                in self.iter_dev_packages()
            }


class MakePkgRepo(Repo):

    def __init__(self):
        Repo.__init__(self, root="rez:package_maker")

    @property
    def makers(self):
        return {
            "os": pkg_os,
            "arch": pkg_arch,
            "platform": pkg_platform,
            "rez": pkg_rez,
        }

    def make_package(self, name):
        func = self.makers.get(name)
        if func is not None:
            maker = func()
            maker.__source__ = self.root
            return maker.get_package()

    def iter_dev_packages(self):
        for name in self.makers:
            package = self.make_package(name)
            data = package.data
            yield name, {data["version"]: data}

    def get_dev_package_versions(self, name):
        package = self.make_package(name)
        if package:
            data = package.data
            version = data.get("version", "_NO_VERSION")

            yield version, data

    def iter_package_names(self):
        for name in self.makers:
            yield name


class DevPkgRepo(Repo):

    def _git_tags(self, url):
        args = ["git", "ls-remote", "--tags", url]
        try:
            output = subprocess.check_output(args, universal_newlines=True)
        except subprocess.CalledProcessError:
            yield "__git_failed__"
        else:
            for line in output.splitlines():
                yield line.split("refs/tags/")[-1]

    def load_dev_packages(self, package):
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
                        yield DeveloperPackage.from_path(pkg_path)
            else:
                yield DeveloperPackage.from_path(pkg_path)

    def generate_dev_packages(self, family):
        for package in family.iter_packages():
            for dev_package in self.load_dev_packages(package):
                data = dev_package.data.copy()
                data["__source__"] = dev_package.filepath
                version = data.get("version", "_NO_VERSION")

                yield version, data

    def iter_dev_packages(self):
        for family in iter_package_families(paths=[self._root]):
            name = family.name  # package dir name
            versions = dict()

            for version, data in self.generate_dev_packages(family):
                versions[version] = data

            yield name, versions

    def get_dev_package_versions(self, name):
        it = iter_package_families(paths=[self._root])
        family = next((f for f in it if f.name == name), None)
        if family is None:
            return

        for version, data in self.generate_dev_packages(family):
            yield version, data

    def iter_package_names(self):
        for family in iter_package_families(paths=[self._root]):
            yield family.name  # package dir name


class DevRepoManager(object):

    def __init__(self):
        deliverconfig = rezconfig.plugins.command.deliver
        maker_repo = MakePkgRepo()
        dev_repos = [
            DevPkgRepo(root=expand_path(root))
            for root in deliverconfig.dev_repository_roots
        ]
        dev_repos += [maker_repo]

        self._all_loaded = False
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

    def load(self, name=None):
        dev_paths = [repo.root for repo in self._dev_repos[:-1]]
        dev_paths.append(self._maker_repo.mem_uid)
        # Note that the maker repo doesn't have filesystem based package,
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

        if not name:
            self._all_loaded = True

    def find(self, request):
        request = PackageRequest(request)
        if not self._all_loaded:
            self.load(name=request.name)
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


class Requested(object):
    __slots__ = ("name", "index", "source", "status", "depended")

    def __init__(self, name, index, source, status, depended=None):
        self.name = name
        self.index = index
        self.source = source
        self.status = status
        self.depended = depended or []

    def __eq__(self, other):
        return other == (self.name, self.index)

    def __repr__(self):
        return "Requested(name='%s', index=%r)" % (self.name, self.index)


class PackageInstaller(object):
    NotInstalled = 0
    Installed = 1
    ResolveFailed = 2

    def __init__(self, dev_repo):
        self.release = False
        self.dev_repo = dev_repo
        self._requirements = list()

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
        self.reset()

    def reset(self):
        self._requirements = []

    def manifest(self):
        return self._requirements[:]

    def run(self):
        for _ in self.run_iter():
            pass

    def run_iter(self):
        for requested in self._requirements:
            if requested.status != self.NotInstalled:
                # TODO: prompt warning if the status is `ResolveFailed`
                continue

            if requested.source == self.dev_repo.maker_root:
                self._make(requested.name,
                           variant=requested.index)
            else:
                self._build(os.path.dirname(requested.name),
                            variant=requested.index)

            yield requested

    def find_installed(self, name):
        paths = self.installed_packages_path
        return get_latest_package_from_string(name, paths=paths)

    def resolve(self, request, variant_index=None, depended=None):
        """"""
        develop = self.dev_repo.find(request)
        package = self.find_installed(request)

        if develop is None and package is None:
            raise PackageNotFoundError("%s not found in develop repository "
                                       "nor in installed package paths."
                                       % request)
        if package is None:
            # use developer package
            name = develop.qualified_name
            variants = develop.iter_variants()
            source = develop.data["__source__"]
            pkg_variants_req = []
        else:
            # use installed package
            name = package.qualified_name
            variants = package.iter_variants()
            source = package.uri
            pkg_variants_req = [v.variant_requires
                                for v in package.iter_variants()]

        for variant in variants:
            if variant_index is not None and variant_index != variant.index:
                continue
            # create/get request item
            exists = variant.variant_requires in pkg_variants_req
            status = self.Installed if exists else self.NotInstalled
            try:
                req_id = self._requirements.index((name, variant.index))
            except ValueError:
                req_id = None
                requested = Requested(name, variant.index, source, status)
            else:
                requested = self._requirements[req_id]
                requested.status = status

            if depended:
                requested.depended.append(depended)

            # solve
            try:
                context = self._build_context(variant)
            except PackageNotFoundError as e:
                print(e)
                requested.status = self.ResolveFailed

            else:
                if not context.success:
                    context.print_info()
                    requested.status = self.ResolveFailed
                else:
                    for pkg in context.resolved_packages:
                        if (pkg.qualified_package_name, pkg.index) in \
                                self._requirements:
                            continue

                        self.resolve(request=pkg.qualified_package_name,
                                     variant_index=pkg.index,
                                     depended=requested)

            if req_id is None:
                self._requirements.append(requested)

    def _build_context(self, variant):
        paths = self.installed_packages_path + self.dev_repo.paths
        implicit_pkgs = list(map(PackageRequest, rezconfig.implicit_packages))
        pkg_requests = variant.get_requires(build_requires=True,
                                            private_build_requires=True)
        return ResolvedContext(pkg_requests + implicit_pkgs,
                               building=True,
                               package_paths=paths)

    def _make(self, name, variant=None):
        deploy_path = self.deploy_path
        if not os.path.isdir(deploy_path):
            os.makedirs(deploy_path)

        made_pkg = self.dev_repo.get_maker_made_package(name)
        made_pkg.__install__(deploy_path)

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


def pkg_os():
    version = system.os
    requires = ["platform-%s" % system.platform,
                "arch-%s" % system.arch]

    def install_os(repo_path):
        with make_package("os", repo_path) as pkg:
            pkg.version = version
            pkg.requires = requires

    maker = PackageMaker("os")
    maker.version = version
    maker.requires = requires
    maker.__install__ = install_os

    return maker


def pkg_arch():
    version = system.arch

    def install_arch(repo_path):
        with make_package("arch", repo_path) as pkg:
            pkg.version = version

    maker = PackageMaker("arch")
    maker.version = version
    maker.__install__ = install_arch

    return maker


def pkg_platform():
    version = system.platform

    def install_platform(repo_path):
        with make_package("platform", repo_path) as pkg:
            pkg.version = version

    maker = PackageMaker("platform")
    maker.version = version
    maker.__install__ = install_platform

    return maker


def pkg_rez():
    version = fetch_rez_version_from_pypi()
    gui_version = version or "2"
    pip_version = ("==%s" % version) if version else ">=2"

    variant = system.variant
    variant.append("python-{0.major}.{0.minor}".format(sys.version_info))

    def install_rez_from_pip(repo_path):
        # pip install rez to temp
        tmpdir = mkdtemp(prefix="rez-install-")
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "rez" + pip_version,
                               "--target", tmpdir])
        # get version info
        dist_version = next(d.version for d in
                            Distribution.discover(name="rez", path=[tmpdir]))

        # make package
        def commands():
            env.PYTHONPATH.append("{this.root}")

        def make_root(variant, root):
            for lib in ["rez", "rezplugins"]:
                shutil.copytree(os.path.join(tmpdir, lib),
                                os.path.join(root, lib))

        with make_package("rez", repo_path, make_root=make_root) as pkg:
            pkg.version = dist_version
            pkg.variants = [variant]
            pkg.commands = commands

        # cleanup
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass

    maker = PackageMaker("rez")
    maker.version = gui_version
    maker.variants = [variant]
    maker.__install__ = install_rez_from_pip

    return maker


def fetch_rez_version_from_pypi():
    history_url = "https://pypi.org/project/rez/#history"
    try:
        response = requests.get(url=history_url, timeout=1)
    except (requests.exceptions.Timeout, requests.exceptions.ProxyError):
        pass
    else:
        matched = _regex_pypi_rez_ver.match(response.text)
        if matched and matched.groups():
            version_str = matched.groups()[0]
            try:
                Version(version_str)
            except VersionError:
                pass
            else:
                return version_str

    print("Failed to parse latest rez version from PyPi..")


_regex_pypi_rez_ver = re.compile('.*<h1 class="package-header__name">'
                                 '.*rez ([0-9]+.[0-9]+.[0-9]+).*',
                                 flags=re.DOTALL)
