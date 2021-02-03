
import sys
import argparse
from . import cli

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
    cli.list_developer_packages(opt.packages)
    sys.exit(0)

if opt.packages:
    if cli.deploy_packages(opt.packages, opt.release, opt.yes):
        print("=" * 30)
        print("SUCCESS!\n")

else:
    print("Please name at least one package to deploy. Use --list to "
          "view available packages.")
