
import re
from deliver import pkgs


def list_developer_packages(requests=None):

    loader = pkgs.PackageLoader()

    if not requests:
        # list all developer package family name
        names = sorted(loader.iter_package_names())
        for n in names:
            print(n)

    else:
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
    variant_index_regex = re.compile(r"(.+)\[([0-9]+)]")

    installer = pkgs.PackageInstaller()
    installer.target(path)

    for req in requests:
        result = variant_index_regex.split(req)
        index = None
        if not result[0]:
            req, index = result[1:3]
            index = int(index)
        installer.resolve(req, variant_index=index)

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
        status = "(%s)" % pkgs.PackageInstaller.StatusMapStr[requested.status]
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
