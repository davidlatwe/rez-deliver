
import sys
import argparse

from .rez import build_rez_via_pip


builders = {
    "rez": build_rez_via_pip,
}


parser = argparse.ArgumentParser("Deliver Make")
parser.add_argument("-n", "--name", required=True)
parser.add_argument("-p", "--path", required=True)
parser.add_argument("--args", nargs="*")

opts = parser.parse_args()

builder = builders[opts.name]
sys.exit(builder(opts.path, *opts.args))
