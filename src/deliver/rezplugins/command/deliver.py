"""
Rez developer package delivering tool
"""
import sys
from rez.command import Command


command_behavior = {}


def setup_parser(parser, completions=False):
    parser.add_argument("packages", nargs="*",
                        help="Package names to deploy.")
    parser.add_argument("-r", "--release", action="store_true",
                        help="Deploy package as release.")
    parser.add_argument("-i", "--install", nargs="?",
                        const=True, default=False,
                        help="Deploy package as install. Packages will be "
                             "installed to a custom path if path given, or "
                             "to Rez local_packages_path by default.")
    parser.add_argument("-l", "--list", action="store_true",
                        help="List out packages that can be deployed. If "
                             "`packages` given, versions will be listed.")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Yes to all.")
    parser.add_argument("--gui", action="store_true",
                        help="Launch GUI.")
    parser.add_argument("--version", action="store_true",
                        help="Print out version of this plugin command.")


def command(opts, parser=None, extra_arg_groups=None):
    from rez.config import config
    from deliver import cli

    # TODO: ensure vcs plugin "kit" is loaded on package release
    # TODO: This deploy script requires to be in rez venv

    if opts.version:
        from deliver._version import print_info
        sys.exit(print_info())

    if opts.gui:
        from deliver.gui import cli as gui
        return gui.main()

    if opts.list:
        cli.list_developer_packages(opts.packages)
        return

    if opts.packages:

        if opts.release and opts.install:
            print("Cannot set both --release and --install flags.")
            return

        if not opts.release and not opts.install:
            print("Must pick one deploy option --release or --install.")
            return

        if opts.install:
            if isinstance(opts.install, bool):
                path = config.local_packages_path
            else:
                path = opts.install
        elif opts.release:
            path = config.release_packages_path
        else:
            raise Exception("Undefined behavior.")

        if cli.deploy_packages(opts.packages, path, opts.yes):
            print("=" * 30)
            print("SUCCESS!\n")

    else:
        print("Please name at least one package to deploy. Use --list to "
              "view available packages.")


class DeliverCommand(Command):
    schema_dict = {
        "dev_repository_roots": list,
        "rez_source_path": str,
        "github_token": str,
        "cache_dev_packages": bool,
        "dev_packages_cache_days": int,
    }

    @classmethod
    def name(cls):
        return "deliver"


def register_plugin():
    return DeliverCommand
