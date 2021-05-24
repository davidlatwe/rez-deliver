
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

    # for case like:
    #
    #   `tests.test_manifest.TestManifest.test_buildtime_variants`
    #
    # which requires to scan packages to list out current available variants,
    # we resolve the request here again and append loader paths for including
    # developer packages in that scan.
    #
    solver = RequestSolver()
    solver.resolve(opts.PKG)

    # build/release
    #
    settings = {
        # developer packages loader paths appended, see comment above.
        "packages_path": solver.installed_packages_path + solver.loader.paths,
    }
    with override_config(settings):
        command = "release" if opts.release else "build"
        sys.argv = ["rez-" + command] + remains
        run(command)


if __name__ == "__main__":
    main()
