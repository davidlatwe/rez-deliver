
import os
import sys


def build(source_path, build_path, install_path, targets=None):
    import shutil

    targets = targets or []

    if "install" in targets:
        dst = install_path
    else:
        dst = build_path

    dst = os.path.normpath(dst)

    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)

    # copy source
    shutil.copytree(os.path.join(source_path, "python"),
                    os.path.join(dst, "python"))


if __name__ == "__main__":
    build(source_path=os.environ["REZ_BUILD_SOURCE_PATH"],
          build_path=os.environ["REZ_BUILD_PATH"],
          install_path=os.environ["REZ_BUILD_INSTALL_PATH"],
          targets=sys.argv[1:])
