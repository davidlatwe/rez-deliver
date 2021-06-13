
from deliver import api


def list_developer_packages(requests=None):
    from rez.utils.formatting import PackageRequest

    loader = api.PackageLoader()

    if not requests:
        # list all developer package family name
        names = sorted(loader.iter_package_family_names())
        for n in names:
            print(n)

    else:
        requests = [PackageRequest(r) for r in requests]

        names = list()
        for request in requests:
            pkg = loader.find(request)
            if pkg is None:
                print("Package not found in this repository: %s" % request)
                continue
            names.append(pkg.name)

        print("\nPackages available in this repository:")
        print("=" * 30)

        for family in loader.iter_package_families():
            if family.name in names:
                for package in family.iter_packages():
                    print(package.qualified_name)


def deploy_packages(requests, path, dry_run=False, yes=False):

    installer = api.PackageInstaller()
    installer.deploy_to(path)

    installer.resolve(*requests)

    manifest = installer.manifest()

    if not manifest:
        print("No package to deploy.")
        return

    names = [
        ("%s" % requested.name)
        + ("" if requested.index is None else ("[%s]" % requested.index))
        for requested in manifest
    ]
    _max_name_len = max(len(n) for n in names)

    print("\nFollowing packages will be deployed:")
    print("-" * 70)
    for i, requested in enumerate(manifest):
        template = " %%-%ds | %%s" % _max_name_len
        status = "(%s)" % api.PackageInstaller.StatusMapStr[requested.status]
        line = template % (names[i], status)
        print(line)

    if dry_run:
        return

    proceed = yes or confirm("Do you want to continue ? [Y/n]\n")
    if not proceed:
        print("Cancelled")
        return

    installer.run()


try:
    _input = raw_input
except NameError:
    _input = input


def confirm(msg):
    try:
        reply = _input(msg).lower().rstrip()
        return reply in ("", "y", "yes", "ok")
    except EOFError:
        return True  # On just hitting enter
    except KeyboardInterrupt:
        return False
