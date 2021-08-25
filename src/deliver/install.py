
import os
import sys
import argparse
import subprocess

from rez.config import config as rezconfig

from deliver.solve import RequestSolver
from deliver.lib import clear_repo_cache, temp_env


class PackageInstaller(RequestSolver):
    """Extended from `RequestSolver` to execute installation"""

    def run(self):
        for _ in self.run_iter():
            pass

    def run_iter(self):
        deliverconfig = rezconfig.plugins.command.deliver

        for requested in self._requirements:
            if requested.status != self.Ready:
                # TODO: prompt warning if the status is `ResolveFailed`
                continue

            if requested.source == self.loader.maker_source:
                self._make(requested.name,
                           variant=requested.index)
            else:
                self._build(requested.name,
                            os.path.dirname(requested.source),
                            variant=requested.index,
                            ver_tag=requested.ver_tag)

            deliverconfig.on_package_deployed_callback(
                name=requested.name,
                path=self.deploy_path,
            )

            yield requested

    def _make(self, name, variant=None):
        deploy_path = self.deploy_path
        if not os.path.isdir(deploy_path):
            os.makedirs(deploy_path)

        made_pkg = self.loader.get_maker_made_package(name)
        made_pkg.__install__(deploy_path, variant)

        clear_repo_cache(deploy_path)

    def _build(self, name, src_dir, variant=None, ver_tag=None):
        variant_cmd = [] if variant is None else ["--variants", str(variant)]
        deploy_path = self.deploy_path

        if not os.path.isdir(deploy_path):
            os.makedirs(deploy_path)

        if variant is not None:
            name += "[%d]" % variant

        env = os.environ.copy()
        cmd = [sys.executable, "-m", "deliver.install", name]

        if self._release:
            env["REZ_RELEASE_PACKAGES_PATH"] = deploy_path
            cmd += ["--release", "--no-latest"]
        else:
            env["REZ_LOCAL_PACKAGES_PATH"] = deploy_path
            cmd += ["--install"]

        if ver_tag:
            env["__DELIVER_PKG_PAYLOAD_VER"] = ver_tag

        cmd += variant_cmd
        self._run_command(cmd, cwd=src_dir, env=env)

        clear_repo_cache(deploy_path)

    def _run_command(self, cmd_args, **kwargs):
        print("Running command:\n    %s\n" % cmd_args)
        subprocess.check_call(cmd_args, **kwargs)


def main():
    from rez.cli._main import run
    from deliver.solve import RequestSolver
    from deliver.lib import override_config

    ver_tag = os.getenv("__DELIVER_PKG_PAYLOAD_VER")

    parser = argparse.ArgumentParser("deliver.install")
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
    with override_config(settings), \
            temp_env("REZ_DELIVER_PKG_PAYLOAD_VER", ver_tag):

        command = "release" if opts.release else "build"
        sys.argv = ["rez-" + command] + remains
        run(command)


if __name__ == "__main__":
    main()
