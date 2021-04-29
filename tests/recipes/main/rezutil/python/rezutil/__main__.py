import sys
import argparse

argv1 = list(sys.argv[1:2])
argv2 = list(sys.argv[2:])

parser = argparse.ArgumentParser("rezutil", add_help=False)
parser.add_argument("command")

if argv1[-1] == ["--help"]:
    parser.print_help()
    exit(0)

opts, unknown = parser.parse_known_args(argv1)

if opts.command == "build":
    from . import _rezbuild
    _rezbuild.main(argv2)

else:
    print(
        "Unsupported command '%s', must be build, "
        "convert or translate" % opts.command
    )
