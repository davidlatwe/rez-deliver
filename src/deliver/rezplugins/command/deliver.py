"""
Rez developer package delivering tool
"""
import sys
import types
import argparse
try:
    from rez.command import Command
except ImportError:
    Command = object


command_behavior = {}


def rez_cli():
    from rez.cli._main import run
    from rez.cli._entry_points import check_production_install
    check_production_install()
    try:
        return run("deliver")
    except KeyError:
        pass
        # for rez version that doesn't have Command type plugin
    return standalone_cli()


def standalone_cli():
    # for running without rez's cli
    parser = argparse.ArgumentParser("deliver")
    setup_parser(parser)
    opts = parser.parse_args()
    return command(opts)


def setup_parser(parser, completions=False):
    parser.add_argument("PKG", nargs="*",
                        help="Package names to deploy.")
    parser.add_argument("-r", "--release", action="store_true",
                        help="Deploy package as release.")
    parser.add_argument("--dry-run", action="store_true",
                        help="List out all packages that will be deployed "
                             "and exit.")
    parser.add_argument("-l", "--list", action="store_true",
                        help="List out packages that can be deployed. If "
                             "`packages` given, versions will be listed.")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Yes to all.")
    parser.add_argument("-G", "--gui", action="store_true",
                        help="Launch GUI.")
    parser.add_argument("--version", action="store_true",
                        help="Print out version of this plugin command.")


def command(opts, parser=None, extra_arg_groups=None):
    from rez.config import config
    from deliver import cli

    if opts.version:
        from deliver._version import print_info
        sys.exit(print_info())

    if opts.gui:
        from deliver.gui import app
        return app.main()

    if opts.list:
        cli.list_developer_packages(opts.PKG)
        return

    if opts.release:
        path = config.release_packages_path
    else:
        path = config.local_packages_path

    if opts.PKG:
        if cli.deploy_packages(opts.PKG, path, opts.dry_run, opts.yes):
            if not opts.dry_run:
                print("=" * 30)
                print("SUCCESS!\n")

    else:
        print("Please name at least one package to deploy. Use --list to "
              "view available packages.")


class DeliverCommand(Command):
    schema_dict = {
        "dev_repository_roots": list,
        "on_package_deployed_callback": types.FunctionType,
    }

    @classmethod
    def name(cls):
        return "deliver"


def register_plugin():
    return DeliverCommand
