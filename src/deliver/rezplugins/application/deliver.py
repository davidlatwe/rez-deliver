"""
Rez developer package delivering tool
"""
from rez.config import PathList, Str
from rez.application import Application
from ._helper import ensure_top_module


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
    parser.add_argument("--version", action="store_true",
                        help="Print out version of this plugin command.")


@ensure_top_module
def command(opts, parser=None, extra_arg_groups=None):
    from deliver._version import version

    if opts.version:
        print(version)
        return


class ApplicationDeliver(Application):
    schema_dict = {
        "dev_repository_roots": PathList,
        "rez_source_path": Str,
        "github_token": Str,
        "cache_dev_packages": bool,
        "dev_packages_cache_days": int,
    }

    @classmethod
    def name(cls):
        return "deliver"


def register_plugin():
    return ApplicationDeliver
