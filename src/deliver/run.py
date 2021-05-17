
import sys
import argparse


def main():
    from rez.cli._main import run
    from deliver.solve import RequestSolver
    from deliver.lib import override_config

    parser = argparse.ArgumentParser("deliver.run")
    parser.add_argument("PKG")
    parser.add_argument("--release", action="store_true")
    opts, remains = parser.parse_known_args()

    solver = RequestSolver()
    solver.resolve(opts.PKG)

    settings = {
        "packages_path": (solver.loader.paths
                          + solver.installed_packages_path),
    }
    with override_config(settings):
        command = "release" if opts.release else "build"
        sys.argv = ["rez-" + command] + remains
        run(command)


if __name__ == "__main__":
    main()
