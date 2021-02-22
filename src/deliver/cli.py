
import os
import argparse
from rez.packages import iter_package_families
from rez.packages import get_latest_package_from_string
from . import pkgs


UserError = type("UserError", (Exception,), {})


def load_userconfig(fname=None):
    from . import deliverconfig

    fname = fname or os.getenv(
        "DELIVER_CONFIG_FILE",
        os.path.expanduser("~/deliverconfig.py")
    )

    mod = {
        "__file__": fname,
    }

    try:
        with open(fname) as f:
            exec(compile(f.read(), f.name, "exec"), mod)

    except IOError:
        raise

    except Exception:
        raise UserError("Better double-check your deliver user config")

    for key in dir(deliverconfig):
        if key.startswith("__"):
            continue

        try:
            value = mod[key]
        except KeyError:
            continue

        setattr(deliverconfig, key, value)

    return fname


def list_developer_packages(requests):

    dev_repo = pkgs.DevPkgManager()
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


def deploy_packages(requests, target, yes=False):
    from .config import config

    dev_repo = pkgs.DevPkgManager()
    installer = pkgs.PackageInstaller(dev_repo)

    if target:
        if target is True:
            target = config.release_targets[0]["name"]

        kwargs = dict()
        for key in config.list_target_required_keys(target):
            value = input_release_param(key)
            if not value:
                print("Cancelled")
                return

            kwargs[key] = value

        try:
            path = installer.target(release=True, name=target, **kwargs)
        except ValueError as e:
            print(str(e))
            return
        else:
            print("\nPackages will be released to:")
            print(path)

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


try:
    _input = raw_input
except NameError:
    _input = input


def input_release_param(key):
    msg = " %s: " % key
    try:
        value = _input(msg).rstrip()
        if not value:
            value = input_release_param(key)
        return value
    except EOFError:
        return input_release_param(key)  # On just hitting enter
    except KeyboardInterrupt:
        return None


def confirm(msg):
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
    # TODO: instead of passing bool, change to pass deliver target name.
    parser.add_argument("-r", "--release", nargs="?",
                        const=True, default=False,
                        help="The name of package releasing target.")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Yes to all.")
    parser.add_argument("-l", "--list", action="store_true",
                        help="List out packages that can be deployed. If "
                             "`packages` given, versions will be listed.")

    opt = parser.parse_args()

    try:
        load_userconfig()
    except IOError:
        pass

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
