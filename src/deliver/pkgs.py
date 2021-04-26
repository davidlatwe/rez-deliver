
import os
import logging
import functools
import subprocess
import contextlib
from collections import OrderedDict

from rez.config import config as rezconfig
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


# silencing rez logger, e.g. on package preprocessing
rez_logger.setLevel(logging.WARNING)

deliverconfig = rezconfig.plugins.command.deliver


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


class BindPkgRepo(Repo):

    @property
    def root(self):
        return self.mem_uid

    @property
    def bindings(self):
        return {
            "os": pkg_os,
            "arch": pkg_arch,
            "platform": pkg_platform,
        }

    def iter_bind_packages(self):
        for name, maker in self.bindings.items():
            data = maker().data.copy()
            data["_DEV_SRC"] = self._root
            yield name, {data["version"]: data}

    def load(self):
        self.mem_repo.data = {
            name: versions for name, versions
            in self.iter_bind_packages()
        }


class DevPkgRepo(Repo):

    def git_tags(self, url):
        args = ["git", "ls-remote", "--tags", url]
        output = subprocess.check_output(args, universal_newlines=True)
        for line in output.splitlines():
            yield line.split("refs/tags/")[-1]

    def generate_dev_packages(self, family):
        for package in family.iter_packages():
            pkg_path = os.path.dirname(package.uri)

            git_url = package.data.get("git_url")
            if git_url:
                for ver_tag in self.git_tags(git_url):

                    os.environ["REZ_DELIVER_PKG_PAYLOAD_VER"] = ver_tag
                    yield DeveloperPackage.from_path(pkg_path)

            else:
                yield DeveloperPackage.from_path(pkg_path)

    def iter_dev_packages(self):
        for family in iter_package_families(paths=[self._root]):
            name = family.name  # package dir name
            versions = dict()

            for dev_package in self.generate_dev_packages(family):
                data = dev_package.data.copy()

                if data.get("_DEV_SRC") != "_REZ_BIND":
                    data["_DEV_SRC"] = dev_package.filepath

                version = data.get("version", "_NO_VERSION")
                versions[version] = data

            yield name, versions

    def load(self):
        """Load dev-packages from filesystem into memory repository"""
        self.mem_repo.data = {
            name: versions for name, versions
            in self.iter_dev_packages()
        }


class DevRepoManager(object):

    def __init__(self):
        self._dev_repos = [
            DevPkgRepo(root=expand_path(root))
            for root in deliverconfig.dev_repository_roots
        ]
        self._bind_repo = BindPkgRepo(root="_REZ_BIND")

    @property
    def binds(self):
        return self._bind_repo

    @property
    def paths(self):
        mem_paths = [
            repo.mem_uid
            for repo in self._dev_repos
        ]
        mem_paths.append(self._bind_repo.mem_uid)

        return mem_paths

    def load(self):
        self._bind_repo.load()

        dev_paths = [
            repo.root
            for repo in self._dev_repos
        ]
        dev_paths.append(self._bind_repo.root)

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
                repo.load()

    def find(self, name):
        return get_latest_package_from_string(name, paths=self.paths)

    def iter_package_families(self):
        for family in iter_package_families(paths=self.paths):
            yield family


class PackageInstaller(object):

    def __init__(self, dev_repo, rezsrc=None):
        rezsrc = expand_path(rezsrc or deliverconfig.rez_source_path)

        self.release = False
        self.dev_repo = dev_repo
        self.rezsrc_path = rezsrc
        self._requirements = OrderedDict()

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
        self._requirements.clear()

    def manifest(self):
        return self._requirements.copy()

    def run(self):
        for _ in self.run_iter():
            pass

    def run_iter(self):
        for (q_name, v_index), (exists, src) in self._requirements.items():
            if exists:
                continue

            name = q_name.split("-", 1)[0]

            if name == "rez":
                self._install_rez_as_package()
            elif name in self.dev_repo.binds.bindings:
                self._bind(name)
            else:
                self._build(os.path.dirname(src), variant=v_index)

            yield q_name, v_index

    def find_installed(self, name):
        paths = self.installed_packages_path
        return get_latest_package_from_string(name, paths=paths)

    def resolve(self, request, variant_index=None):
        """"""
        develop = self.dev_repo.find(request)
        package = self.find_installed(request)

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
            source = develop.data["_DEV_SRC"]

        if package is None:
            pkg_variants_req = []
        else:
            pkg_variants_req = [v.variant_requires
                                for v in package.iter_variants()]

        for variant in variants:
            if variant_index is not None and variant_index != variant.index:
                continue

            exists = variant.variant_requires in pkg_variants_req

            context = self._build_context(variant)
            for pkg in context.resolved_packages:
                self.resolve(request=pkg.qualified_package_name,
                             variant_index=pkg.index)

            self._requirements[(name, variant.index)] = (exists, source)

    def _install_rez_as_package(self):
        """Use Rez's install script to deploy rez as package
        """
        rezsrc = self.rezsrc_path
        deploy_path = self.deploy_path

        rez_install = os.path.join(os.path.abspath(rezsrc), "install.py")
        dev_pkg = self.dev_repo.find("rez")

        print("Installing Rez as package..")

        clear_repo_cache(deploy_path)

        for variant in dev_pkg.iter_variants():
            print("Variant: ", variant)

            context = self._build_context(variant)
            context.execute_shell(
                command=["python", rez_install, "-v", "-p", deploy_path],
                block=True,
                cwd=rezsrc,
            )

    def _build_context(self, variant):
        paths = self.installed_packages_path + self.dev_repo.paths
        implicit_pkgs = list(map(PackageRequest, rezconfig.implicit_packages))
        pkg_requests = variant.get_requires(build_requires=True,
                                            private_build_requires=True)
        return ResolvedContext(pkg_requests + implicit_pkgs,
                               building=True,
                               package_paths=paths)

    def _bind(self, name):
        pkg = self.find_installed(name)
        if pkg is not None:
            # installed
            return

        deploy_path = self.deploy_path
        env = os.environ.copy()

        if not os.path.isdir(deploy_path):
            os.makedirs(deploy_path)

        if self.release:
            env["REZ_RELEASE_PACKAGES_PATH"] = deploy_path
            self._run_command(["rez-bind", "--release", name], env=env)
        else:
            env["REZ_LOCAL_PACKAGES_PATH"] = deploy_path
            self._run_command(["rez-bind", name])

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
def override_config(entries):
    try:
        for key, value in entries.items():
            rezconfig.override(key, value)
        yield

    finally:
        for key in entries.keys():
            rezconfig.remove_override(key)


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
