from __future__ import absolute_import
import re
import os
import shutil
import subprocess
from tempfile import mkdtemp

from rez.util import which
from rez.system import system
from rez.utils.lint_helper import env
from rez.packages import iter_packages
from rez.config import config as rezconfig
from rez.resolved_context import ResolvedContext
from rez.package_maker import PackageMaker, make_package
from rez.vendor.version.version import Version, VersionError


def fetch_rez_version_from_pypi():
    try:
        from urllib.request import urlopen  # noqa, py3
    except ImportError:
        from urllib import urlopen  # noqa, py2

    name = "rez"

    _pypi_url = "https://pypi.python.org/simple/{}".format(name)
    _regex_version = re.compile(".*{}-(.*)\\.tar\\.gz".format(name))

    f = urlopen(_pypi_url)
    text = f.read().decode("utf-8")
    f.close()

    latest_str = ""
    for line in text.split():
        result = _regex_version.search(line)
        if result:
            latest_str = result.group(1)

    try:
        Version(latest_str)
    except VersionError:
        pass
    else:
        return latest_str

    print("Failed to parse latest rez version from PyPi..")


_regex_pypi_rez_ver = re.compile('.*<h1 class="package-header__name">'
                                 '.*rez ([0-9]+.[0-9]+.[0-9]+).*',
                                 flags=re.DOTALL)


def find_python_package_versions(release):
    from deliver.api import PackageLoader

    python = "python"
    versions = set()

    loader = PackageLoader()

    paths = rezconfig.nonlocal_packages_path[:] if release \
        else rezconfig.packages_path[:]
    paths += loader.paths

    for package in iter_packages(python, paths=paths):
        versions.add(package.version)

    short_versions = set()
    for version in sorted(versions):
        tokens = [
            str(t) for t in version.tokens[:2]  # only need major.minor
        ]
        if len(tokens) >= 2 and all(t.isdigit() for t in tokens):
            short_versions.add(".".join(tokens))

    return sorted(short_versions)


def pkg_rez(release, *_args, **_kwargs):
    version = fetch_rez_version_from_pypi()
    gui_version = version or "2"
    pip_version = ("==%s" % version) if version else ">=2"

    variants = []
    pythons = find_python_package_versions(release)

    if pythons:
        for py_ver in pythons:
            variant = system.variant[:]
            variant.append("python-" + py_ver)
            variants.append(variant)

        def install_rez_via_pip(repo_path, variant_index, *_args, **_kwargs):
            py_version = pythons[variant_index]
            requires = variants[variant_index]
            context = ResolvedContext(requires, building=True)

            _exec = context.which("_deliver_mk")
            if not _exec:
                raise Exception("Could not found executable '_deliver_mk' "
                                "within package building context, possible "
                                "not a production install ?")

            context.execute_shell(
                command=[_exec,
                         "-n", "rez",
                         "-p", repo_path,
                         "--args",
                         "rez" + pip_version,
                         gui_version,
                         py_version],
                block=True,
            )

    else:
        # no python package found, install as python-any
        variant = system.variant[:]
        variants.append(variant)

        def install_rez_via_pip(repo_path, *_args, **_kwargs):
            build_rez_via_pip(repo_path,
                              "rez" + pip_version,
                              gui_version,
                              python_version=None)

    maker = PackageMaker("rez")
    maker.version = gui_version
    maker.variants = variants
    maker.__install__ = install_rez_via_pip

    return maker


def build_rez_via_pip(repo_path, rez_url, rez_version, python_version=None):
    # pip install rez to temp
    tmpdir = mkdtemp(prefix="rez-install-")
    python_exec = which("python")

    subprocess.check_call(
        [python_exec, "-m", "pip", "install", rez_url, "--target", tmpdir],
        stderr=subprocess.STDOUT,
    )

    # make package
    def commands():
        env.PYTHONPATH.append("{this.root}")

    def make_root(_variant, root):
        for lib in ["rez", "rezplugins"]:
            shutil.copytree(os.path.join(tmpdir, lib),
                            os.path.join(root, lib))

    variant = system.variant[:]
    if python_version:
        variant.append("python-%s" % python_version)
    variants = [variant]

    with make_package("rez", repo_path, make_root=make_root) as pkg:
        pkg.version = rez_version
        pkg.variants = variants
        pkg.commands = commands

    # cleanup
    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
