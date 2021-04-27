
from . import pkgs


def list_developer_packages(requests=None):

    dev_repo = pkgs.DevRepoManager()

    if not requests:
        # list all developer package family name
        names = sorted(dev_repo.iter_package_names())
        for n in names:
            print(n)

    else:
        names = list()
        for request in requests:
            pkg = dev_repo.find(request)
            if pkg is None:
                print("Package not found in this repository: %s" % request)
                continue
            names.append(pkg.name)

        print("\nPackages available in this repository:")
        print("=" * 30)

        for family in dev_repo.iter_package_families():
            if family.name in names:
                for package in family.iter_packages():
                    print(package.qualified_name)


def deploy_packages(requests, path, dry_run=False, yes=False):

    dev_repo = pkgs.DevRepoManager()
    installer = pkgs.PackageInstaller(dev_repo)
    installer.target(path)

    # variant specification isn't support in CLI mode
    for req in requests:
        installer.resolve(req)

    manifest = installer.manifest()

    names = [
        ("%s" % name) + ("" if variant_ind is None else ("[%s]" % variant_ind))
        for name, variant_ind in manifest.keys()
    ]
    _max_name_len = max(len(n) for n in names)

    print("\nFollowing packages will be deployed:")
    print("-" * 70)
    for i, (exists, src) in enumerate(manifest.values()):
        template = " %%-%ds | %%s" % _max_name_len
        line = template % (names[i], "(installed)" if exists else src)
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
