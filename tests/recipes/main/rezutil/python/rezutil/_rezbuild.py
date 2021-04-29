# -*- coding: utf-8 -*-

import os
import sys
import stat
import time
import errno
import shutil
import fnmatch
import zipfile
import logging

logging.basicConfig(format="%(msg)s")
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# Internal Rez-specific ignores that are always included
_IGNORE = [
    "package.py",
    "rezbuild.py",
    "build",
]

# Include all files from a package, except these
# Think of these as a `.gitignore`
IGNORE = [
    ".git",
    "doc",
    "docs",
    "*.pyc",
    ".cache",
    "__pycache__",
    "*.pyproj",
    "*.sln",
    ".vs",
]

# IO is unreliable; in this script, we'll give
# it this many attempts before throwing our hands up
RETRY = 3

try:
    # For Python 2
    unicode
except NameError:
    unicode = str


def retry(func):
    def decorator(*args, **kwargs):

        # Give targets a chance to handle
        # each retry differently
        kwargs["attempt"] = 0

        for retry_ in range(RETRY):
            try:
                return func(*args, **kwargs)

            except Exception:
                kwargs["attempt"] += 1
                tell("Retrying (%d/%d).." % (retry_ + 1, RETRY), 3)

                # Wait increasingly longer
                time.sleep(0.5 * (retry_ or 0.2))

        else:
            import traceback
            traceback.print_exc()
            raise Exception(
                "{func} was attempted {count} "
                "times, but failed".format(
                    func=func.__name__,
                    count=RETRY,
                ))

    return decorator


def tell(msg, level=0):
    try:
        log.info(" " * level + str(msg.encode("utf-8")))
    except Exception:
        # Logging must never throw an exception
        # This may happen on e.g. UnicodeDecodeError
        import traceback
        traceback.print_exc()


def ignored(abspath):
    """Determine whether `abspath` should be excluded"""
    basename = os.path.basename(abspath)
    return any(
        fnmatch.filter([basename], i)
        for i in IGNORE + _IGNORE
    )


@retry
def makedirs(path, attempt=0):
    dirname = os.path.dirname(path)

    try:
        os.makedirs(dirname)
    except OSError as e:
        if e.errno is errno.EEXIST:
            # Jobs already done
            return

        # Unexpected
        raise


def generate_manifest(root):
    for base, dirs, files in os.walk(root):
        if ignored(base):
            dirs[:] = []  # Don't continue down this hierarchy
            continue

        for fname in files:

            # Ignore unicode filenames
            if "?" in fname:
                continue

            abspath = os.path.join(base, fname)
            relpath = os.path.relpath(abspath, root)

            if ignored(relpath):
                continue

            yield relpath


@retry
def clean(root, attempt=0):
    from .lib import path_fix

    for base, dirs, files in os.walk(unicode(root)):
        # All directories
        for dirname in dirs:
            abspath = os.path.join(base, dirname)
            tell("Removing dir %s" % dirname, 6)

            def del_rw(action, name, exc):
                # handling read-only files, e.g. in .git
                name = path_fix(name)
                os.chmod(name, stat.S_IWRITE)
                os.remove(name)

            shutil.rmtree(abspath, onerror=del_rw)

        # And files
        for fname in files:
            abspath = os.path.join(base, fname)

            if attempt == 0:
                tell("Removing file %s" % fname, 6)

            if attempt == 1:
                tell("Editing file permissions..", 6)
                os.chmod(abspath, stat.S_IWRITE | stat.S_IREAD)

            os.remove(abspath)


@retry
def copy_with_retry(src, dst, attempt=0):
    shutil.copy(src, dst)


def build(source_path, build_path, install_path=None, targets=None):
    targets = targets or []
    manifest = list(generate_manifest(source_path))

    def _copy():
        if os.path.exists(build_path):
            tell("Cleaning previous build..", 3)
            clean(build_path)

        for relpath in manifest:
            tell("Writing %s" % relpath, 3)
            src = os.path.join(source_path, relpath)
            dst = os.path.join(build_path, relpath)
            makedirs(dst)
            copy_with_retry(src, dst)

    def _install():
        if os.path.exists(install_path):
            tell("Cleaning previous install..", 3)
            clean(install_path)

        for relpath in manifest:
            tell("Installing %s" % relpath, 3)
            src = os.path.join(build_path, relpath)
            dst = os.path.join(install_path, relpath)
            makedirs(dst)
            copy_with_retry(src, dst)

    _copy()

    if "install" in targets:
        _install()


def pipz_build(source_path, build_path, install_path, targets=None):
    try:
        from pipz import pip
    except ImportError:
        raise ImportError("rez-pipz package required.")

    targets = targets or []

    def _pipz():
        if os.path.exists(build_path):
            tell("Cleaning previous build..", 3)
            clean(build_path)

        name = "%s==%s" % (os.environ["REZ_BUILD_PROJECT_NAME"],
                           os.environ["REZ_BUILD_PROJECT_VERSION"])
        tell("Downloading %s.." % name, 3)
        new = pip.install(
            names=[name],
            prefix=build_path,
            extra_args=["--no-deps"],
        )[0]  # Must be one and only one downloaded.

        installed_path = os.path.join(build_path, new.name)
        payload_path = os.path.join(installed_path,
                                    str(new.version),
                                    *[str(v) for v in new.variants[0]])

        # pull it out
        for item in os.listdir(payload_path):
            shutil.move(os.path.join(payload_path, item), build_path)
        shutil.rmtree(installed_path)

    def _install():
        if os.path.exists(install_path):
            tell("Cleaning previous install..", 3)
            clean(install_path)

        for relpath in os.listdir(build_path):
            tell("Installing %s" % relpath, 3)
            src = os.path.join(build_path, relpath)
            dst = os.path.join(install_path, relpath)
            shutil.copytree(src, dst)

    _pipz()

    if "install" in targets:
        _install()


def zip_build(source_path, build_path, install_path, targets=None):
    zip_root = os.getenv("REZUTIL_ZIP_ROOT")
    if zip_root is None:
        raise Exception("'REZUTIL_ZIP_ROOT' not set, archive repository "
                        "unknown.")

    pkg_name = os.environ["REZ_BUILD_PROJECT_NAME"]
    pkg_vers = os.environ["REZ_BUILD_PROJECT_VERSION"]
    variant_path = os.environ["REZ_BUILD_VARIANT_SUBPATH"]

    # Strip internal release number, e.g. `x.y.z.rez1`
    ver_info = pkg_vers.rsplit(".", 1)
    if ver_info[-1].startswith("rez"):
        pkg_vers = ver_info[0]

    # Strip internal release number, e.g. `x.y.z-m1`
    ver_info = pkg_vers.rsplit("-", 1)
    if ver_info[-1].startswith("m"):
        pkg_vers = ver_info[0]

    resource = os.path.join(zip_root, pkg_name, pkg_vers, variant_path)
    if not os.path.isdir(resource):
        raise Exception("Path not exists: %s" % resource)

    for item in os.listdir(resource):
        if item.endswith(".zip"):
            zip_file = os.path.join(resource, item)
            break
    else:
        raise Exception("No zip file in %s" % resource)

    targets = targets or []

    def _unzip():
        if os.path.exists(build_path):
            tell("Cleaning previous build..", 3)
            clean(build_path)

        tell("Unzipping : %s" % zip_file)
        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(build_path)

    def _install():
        if os.path.exists(install_path):
            tell("Cleaning previous install..", 3)
            clean(install_path)

        for relpath in os.listdir(build_path):
            tell("Installing %s" % relpath, 3)
            src = os.path.join(build_path, relpath)
            dst = os.path.join(install_path, relpath)
            if os.path.isfile(src):
                shutil.copy(src, dst)
            else:
                shutil.copytree(src, dst)

    _unzip()

    if "install" in targets:
        _install()


def main(argv):
    import argparse

    parser = argparse.ArgumentParser("rezbuild")

    parser.add_argument("source_path", type=str)
    parser.add_argument("--use-pipz", action="store_true")
    parser.add_argument("--use-zip", action="store_true")
    parser.add_argument("--ignore", default=",".join(IGNORE))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--retries", type=int, default=RETRY)
    parser.add_argument("--build_path",
                        type=str,
                        default=os.getenv("REZ_BUILD_PATH"))
    parser.add_argument("--install_path",
                        type=str,
                        default=os.getenv("REZ_BUILD_INSTALL_PATH"))
    parser.add_argument("--install", type=bool,
                        default=bool(int(os.getenv("REZ_BUILD_INSTALL", "0"))))

    opts = parser.parse_args(argv)

    if opts.ignore:
        IGNORE[:] = opts.ignore.split(",")

    if opts.quiet:
        log.setLevel(logging.ERROR)

    targets = ["install"] if opts.install else []

    if opts.use_pipz:
        builder = pipz_build
    elif opts.use_zip:
        builder = zip_build
    else:
        builder = build

    builder(opts.source_path,
            opts.build_path,
            opts.install_path,
            targets)


if __name__ == '__main__':
    main(sys.argv)
