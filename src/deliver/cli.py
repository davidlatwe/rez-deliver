
import argparse
from rez.packages import iter_package_families
from rez.packages import get_latest_package_from_string
from . import pkgs


ROOT = "C:/Users/davidlatwe.lai/pipeline/rez-kit"
ROOT = "C:/Users/davidlatwe.lai/pipeline/rez-deliver/test"
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

    # variant specification isn't support in CLI mode
    for req in requests:
        installer.resolve(req)

    manifest = installer.manifest()

    names = [("%s" % n) + ("" if i is None else ("[%s]" % i))
             for n, i in manifest.keys()]
    _max_name_len = len(max(names))

    print("\nFollowing packages will be deployed:")
    print("-" * 70)
    for i, (exists, src) in enumerate(manifest.values()):
        template = " %%-%ds -> %%s" % _max_name_len
        line = template % (names[i], "(installed)" if exists else src)
        print(line)

    proceed = yes or confirm("Do you want to continue ? [Y/n]\n")
    if not proceed:
        print("Cancelled")
        return

    installer.run()


def confirm(msg):
    try:
        _input = raw_input
    except NameError:
        _input = input

    try:
        reply = _input(msg).lower().rstrip()
        return reply in ("", "y", "yes", "ok")
    except EOFError:
        return True  # On just hitting enter
    except KeyboardInterrupt:
        return False


def main():
    # TODO: ensure vcs plugin "kit" is loaded on package release
    # TODO: This deploy script requires to be in rez venv

    parser = argparse.ArgumentParser()
    parser.add_argument("packages", nargs="*",
                        help="Package names to deploy.")
    parser.add_argument("--release", action="store_true",
                        help="Deploy to package releasing location.")
    parser.add_argument("--yes", action="store_true",
                        help="Yes to all.")
    parser.add_argument("--list", action="store_true",
                        help="List out packages that can be deployed. If "
                             "`packages` given, versions will be listed.")

    opt = parser.parse_args()

    if opt.list:
        list_developer_packages(opt.packages)
        return

    if opt.packages:
        if deploy_packages(opt.packages, opt.release, opt.yes):
            print("=" * 30)
            print("SUCCESS!\n")

    else:
        print("Please name at least one package to deploy. Use --list to "
              "view available packages.")
