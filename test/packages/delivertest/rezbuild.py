
import os
import sys


url_prefix = "https://github.com/%s/archive" % os.environ["GITHUB_REPO"]
filename = "{ver}.zip"


def build(source_path, build_path, install_path, targets=None):
    from rezutil import lib

    targets = targets or []

    if "install" in targets:
        dst = install_path + "/payload"
    else:
        dst = build_path + "/payload"

    dst = os.path.normpath(dst)

    if os.path.isdir(dst):
        lib.clean(dst)

    build_version = os.environ["REZ_BUILD_PROJECT_VERSION"]
    payload_version = build_version.rsplit("-", 1)[0]

    if os.getenv(""):
        # Source from local dev repo
        source_root = os.getenv("REZ_DELIVER_PKG_DEV_ROOT")
    else:
        # Download the source
        url = "%s/%s" % (url_prefix, filename.format(ver=payload_version))
        archive = lib.download(url, filename.format(ver=payload_version))

        # Unzip the source
        source_root = lib.open_archive(archive)

    # Deploy
    lib.copy_dir(source_root, dst)


if __name__ == "__main__":
    build(source_path=os.environ["REZ_BUILD_SOURCE_PATH"],
          build_path=os.environ["REZ_BUILD_PATH"],
          install_path=os.environ["REZ_BUILD_INSTALL_PATH"],
          targets=sys.argv[1:])
