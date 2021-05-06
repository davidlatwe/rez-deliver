from __future__ import absolute_import
import re
import os
import sys
import shutil
import subprocess
from tempfile import mkdtemp

import deliver
import rez
from rez.system import system
from rez.utils.lint_helper import env
from rez.packages import iter_packages
from rez.config import config as rezconfig
from rez.resolved_context import ResolvedContext
from rez.package_maker import PackageMaker, make_package
from rez.vendor.version.version import Version, VersionError


def fetch_rez_version_from_pypi():
    import requests

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


def find_python_package_versions(release):
    from deliver.pkgs import PackageLoader

    python = "python"
    versions = set()

    loader = PackageLoader()
    loader.load(name=python)

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
            requires = variants[variant_index]
            parent_env = os.environ.copy()
            parent_env["PYTHONPATH"] = os.pathsep.join(
                [os.path.dirname(rez.__path__[0])]
                + [os.path.dirname(deliver.__path__[0])]
                + parent_env.get("PYTHONPATH", "").split(os.pathsep))

            context = ResolvedContext(requires, building=True)
            context.execute_shell(
                command=["python", "-m", "deliver.maker",
                         "-n", "rez",
                         "-p", repo_path,
                         "--args",
                         "rez" + pip_version,
                         gui_version],
                parent_environ=parent_env,
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
                              python_variants=False)

    maker = PackageMaker("rez")
    maker.version = gui_version
    maker.variants = variants
    maker.__install__ = install_rez_via_pip

    return maker


def build_rez_via_pip(repo_path, rez_url, rez_version, python_variants=True):
    # pip install rez to temp
    tmpdir = mkdtemp(prefix="rez-install-")
    subprocess.check_call([sys.executable, "-m", "pip", "install", rez_url,
                           "--target", tmpdir])

    # make package
    def commands():
        env.PYTHONPATH.append("{this.root}")

    def make_root(_variant, root):
        for lib in ["rez", "rezplugins"]:
            shutil.copytree(os.path.join(tmpdir, lib),
                            os.path.join(root, lib))

    variant = system.variant[:]
    if python_variants:
        variant.append("python-{0.major}.{0.minor}".format(sys.version_info))
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
