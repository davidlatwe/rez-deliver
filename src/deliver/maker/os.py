from __future__ import absolute_import
from rez.system import system
from rez.package_maker import PackageMaker, make_package


def pkg_os(*_args, **_kwargs):
    version = system.os
    requires = ["platform-%s" % system.platform,
                "arch-%s" % system.arch]

    def install_os(repo_path, *_args, **_kwargs):
        with make_package("os", repo_path) as pkg:
            pkg.version = version
            pkg.requires = requires

    maker = PackageMaker("os")
    maker.version = version
    maker.requires = requires
    maker.__install__ = install_os

    return maker
