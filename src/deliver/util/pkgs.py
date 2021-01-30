
import os
import logging
import subprocess
from collections import OrderedDict
from rez.config import config
from rez.package_maker import PackageMaker
from rez.packages import iter_package_families
from rez.utils.formatting import PackageRequest
from rez.resolved_context import ResolvedContext
from rez.developer_package import DeveloperPackage
from rez.packages import get_latest_package_from_string
from rez.package_repository import package_repository_manager


def deploy_package(request, package_paths=None, yes=False):

    dependencies = dependencies_to_deploy(request)

    if dependencies:
        _max_name_len = len(max(dependencies.keys()))

        print("\nFollowing packages will be deployed:")
        print("-" * 70)
        for q_name, _uri in dependencies.items():
            line = " %%-%ds -> %%s" % _max_name_len
            print(line % (q_name, _uri))

        proceed = yes or lib.confirm("Do you want to continue ? [Y/n]\n")
        if not proceed:
            print("Cancelled")
            return

        # Deploy
        for q_name, _uri in dependencies.items():
            if q_name.startswith("rez-"):
                clear_repo_cache()
                install_rez_as_package(package_paths)
                continue

            args = _state["install_cmd"]
            subprocess.check_call(args, cwd=os.path.dirname(_uri))

    else:
        print("Package %r already been installed." % request)

    return True


def in_memory(pkg):
    return pkg.parent.repository.name() == "memory"


def dependencies_to_deploy(name):
    """"""
    is_installed = False
    to_install = OrderedDict()

    pkg_to_deploy = get_latest_package_from_string(name,
                                                   paths=package_paths)
    if pkg_to_deploy is None:
        uri = None
        variants = []  # dev package might not exists
    else:
        name = pkg_to_deploy.qualified_name
        variants = pkg_to_deploy.iter_variants()
        # TODO: check all variants are installed

        if in_memory(pkg_to_deploy):
            uri = pkg_to_deploy.data["_uri"]
        else:
            uri = pkg_to_deploy.uri
            is_installed = True

    for variant in variants:
        context = get_build_context(variant, package_paths)
        for package in context.resolved_packages:
            dep_name = package.qualified_package_name

            if in_memory(package):
                # need install
                to_install.update(dependencies_to_deploy(dep_name))

            else:
                # already installed
                pass

    if not is_installed:
        to_install[name] = uri

    return to_install


def developer_packages_to_memory():
    """Collect and save developer packages into memory repository

    By making packages from developer packages, and saving them into Rez's
    memory repository, we can then resolve requests to see if any package
    is resolved from memory, and deployed it.

    """
    packages = dict()

    # Append _dev_dirs into packages_path so the requires can be expanded.
    # If we don't do this, requirements like "os-*" or "python-2.*" may fail
    # the schema validation due to the required package is not yet installed.
    config.override("packages_path", config.packages_path[:] + _dev_dirs)
    # Ensure unversioned package is allowed, so we can iter dev packages.
    config.override("allow_unversioned_packages", True)

    for family in iter_package_families(paths=_dev_dirs):
        name = family.name  # package dir name
        versions = dict()

        for _pkg in family.iter_packages():
            data = _pkg.data.copy()
            name = data["name"]  # real name in package.py

            if data.get("github_repo"):
                repo = data["github_repo"]
                # get latest release, and mark unavailable if None.
                result = next(deliver.get_releases(repo, latest=True))
                if result:
                    os.environ["GITHUB_REZ_PKG_PAYLOAD_VER"] = result[0]

            maker = PackageMaker(name,
                                 data=data,
                                 package_cls=DeveloperPackage)
            package = maker.get_package()
            data = package.data.copy()

            # preprocessing
            result = package._get_preprocessed(data)
            if result:
                package, data = result

            data["_uri"] = _pkg.uri
            version = data.get("version", "unversioned")
            versions[version] = data

        packages[name] = versions

    # save collected dev packages in memory repository
    memory_repo = package_repository_manager.get_repository(_memory)
    memory_repo.data = packages

    config.remove_override("packages_path")
    config.remove_override("allow_unversioned_packages")


def get_build_context(variant, package_paths=None):
    implicit_pkgs = list(map(PackageRequest, config.implicit_packages))
    pkg_requests = variant.get_requires(build_requires=True,
                                        private_build_requires=True)
    return ResolvedContext(pkg_requests + implicit_pkgs,
                           building=True,
                           package_paths=package_paths)


def install_rez_as_package(package_paths):
    """Use Rez's install script to deploy rez as package
    """
    from rez.packages import get_latest_package_from_string

    rez_install = os.path.join(os.path.abspath(REZ_SRC), "install.py")
    dev_pkg = get_latest_package_from_string("rez", paths=[_memory])
    dst = _state["install_path"]

    print("Installing Rez as package..")

    for variant in dev_pkg.iter_variants():
        print("Variant: ", variant)

        context = get_build_context(variant, package_paths)
        context.execute_shell(
            command=["python", rez_install, "-v", "-p", dst],
            block=True,
            cwd=REZ_SRC,
        )


def clear_repo_cache(path=None):
    """Clear filesystem repo family cache after pkg bind/install

    Current use case: Clear cache after rez-bind and before iter dev
    packages into memory. Without this, variants like os-* may not be
    expanded due to filesystem repo doesn't know 'os' has been bind since
    the family list is cached in this session.

    """
    path = path or _state["install_path"]
    fs_repo = package_repository_manager.get_repository(path)
    fs_repo.get_family.cache_clear()


def bind(name):
    pkg = get_latest_package_from_string(name, paths=_state["packages_path"])
    if pkg is None:
        subprocess.check_call(_state["bind_cmd"] + [name])
        clear_repo_cache()
