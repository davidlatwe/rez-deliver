
from rez.packages import iter_package_families
from rez.packages import get_latest_package_from_string
from . import pkgs


ROOT = "C:/Users/davidlatwe.lai/pipeline/rez-kit"
REZ_SRC = "C:/Users/davidlatwe.lai/pipeline/rez"


def list_developer_packages(requests):

    dev_repo = pkgs.DevPkgRepository(ROOT)
    dev_repo.reload()

    requests = requests or []

    names = list()
    for request in requests:
        pkg = get_latest_package_from_string(request, paths=[dev_repo.uri()])
        if pkg is None:
            print("Package not found in this repository: %s" % request)
            continue
        names.append(pkg.name)

    print("\nPackages available in this repository:")
    print("=" * 30)

    for family in iter_package_families(paths=[dev_repo.uri()]):
        if not requests:
            print(family.name)
        else:
            if family.name not in names:
                continue

            for package in family.iter_packages():
                print(package.qualified_name)


def deploy_packages(requests, release, yes=False):
    dev_repo = pkgs.DevPkgRepository(ROOT)
    installer = pkgs.PackageInstaller(dev_repo, REZ_SRC, release=release)

    dev_repo.reload()

    installer.run(requests)

    # for request in requests:
    #     print("Processing deploy request: %s .." % request)
    #     deployed = deploy_package(request, package_paths, yes)
    #     if not deployed:
    #         break
    # else:
    #     return True
