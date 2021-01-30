

def print_developer_packages(requests):
    from rez.utils.logging_ import logger
    from rez.packages import (
        iter_package_families,
        get_latest_package_from_string,
    )

    logger.setLevel(logging.WARNING)

    requests = requests or []
    _before_deploy()

    names = list()
    for request in requests:
        pkg = get_latest_package_from_string(request, paths=[_memory])
        if pkg is None:
            print("Package not found in this repository: %s" % request)
            continue
        names.append(pkg.name)

    print("\nPackages available in this repository:")
    print("=" * 30)

    for family in iter_package_families(paths=[_memory]):
        if not requests:
            print(family.name)
        else:
            if family.name not in names:
                continue

            for package in family.iter_packages():
                print(package.qualified_name)


def deploy_packages(requests, yes=False):
    from rez.utils.logging_ import logger

    logger.setLevel(logging.WARNING)

    # TODO: should be in memory
    bind("os")
    bind("arch")
    bind("platform")

    _before_deploy()

    package_paths = _state["packages_path"] + [_memory]

    for request in requests:
        print("Processing deploy request: %s .." % request)
        deployed = deploy_package(request, package_paths, yes)
        if not deployed:
            break
    else:
        return True
