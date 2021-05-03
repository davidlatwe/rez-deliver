from __future__ import absolute_import
from rez.system import system
from rez.package_maker import PackageMaker, make_package


def pkg_arch(*_args, **_kwargs):
    version = system.arch

    def install_arch(repo_path, *_args, **_kwargs):
        with make_package("arch", repo_path) as pkg:
            pkg.version = version

    maker = PackageMaker("arch")
    maker.version = version
    maker.__install__ = install_arch

    return maker
