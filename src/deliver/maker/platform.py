from __future__ import absolute_import
from rez.system import system
from rez.package_maker import PackageMaker, make_package


def pkg_platform(*_args, **_kwargs):
    version = system.platform

    def install_platform(repo_path, *_args, **_kwargs):
        with make_package("platform", repo_path) as pkg:
            pkg.version = version

    maker = PackageMaker("platform")
    maker.version = version
    maker.__install__ = install_platform

    return maker
