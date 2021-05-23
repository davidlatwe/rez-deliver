
import sys
import argparse


def main():
    from rez.cli._main import run
    from rez.packages import get_latest_package
    from rez.package_repository import package_repository_manager
    from deliver.solve import RequestSolver, split_variant_request
    from deliver.lib import override_config

    parser = argparse.ArgumentParser("deliver.run")
    parser.add_argument("PKG")
    parser.add_argument("--release", action="store_true")
    opts, remains = parser.parse_known_args()

    solver = RequestSolver()
    solver.resolve(opts.PKG)

    # staging
    # for case like: tests.test_manifest.TestManifest.test_buildtime_variants
    #
    request, _ = split_variant_request(opts.PKG)
    developer = get_latest_package(request.name,
                                   range_=request.range,
                                   paths=solver.loader.paths)

    stage_path = "memory@" + developer.repository.location
    stage = package_repository_manager.get_repository(stage_path)
    stage.data.update({
        developer.name: {
            str(developer.version) or "_NO_VERSION": developer.data.copy(),
        }
    })

    # build/release
    #
    settings = {
        "packages_path": ([stage_path]
                          + solver.installed_packages_path),
    }
    with override_config(settings):
        command = "release" if opts.release else "build"
        sys.argv = ["rez-" + command] + remains
        run(command)


if __name__ == "__main__":
    main()
