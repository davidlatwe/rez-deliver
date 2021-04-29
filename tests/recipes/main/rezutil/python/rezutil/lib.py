
import os
import sys
import glob
import shlex
import shutil
import fnmatch
import tarfile
import zipfile
import platform
import contextlib
import subprocess
from . import _rezbuild

PY3 = sys.version_info[0] == 3
IS_WIN = platform.system() == "Windows"
IS_LNX = platform.system() == "Linux"
IS_MAC = platform.system() == "Darwin"


def download(url, file_name, dst_dir=None):
    """Download file into current dir or `dst_dir` or `REZ_DOWNLOAD_DIR` env

    Download will be skipped if file existed.

    """
    # https://stackoverflow.com/a/22776/14054728
    if PY3:
        import urllib.request as urllib
    else:
        import urllib2 as urllib

    dst_dir = dst_dir or os.getenv("REZ_DOWNLOAD_DIR", "")
    file_path = os.path.abspath(os.path.join(dst_dir, file_name))

    if os.path.isfile(file_path):
        print("File exists, skip download: %s" % file_path)
        return file_path

    print("Downloading from %s\n\t-> %s" % (url, file_path))
    u = urllib.urlopen(url)
    f = open(file_path, "wb")

    # Get content length (file size)
    #
    meta = u.info()
    try:
        if hasattr(meta, "getheader"):
            file_size = int(meta.getheaders("Content-Length")[0])
        else:
            file_size = int(meta.get("Content-Length")[0])
        print("Downloading: %s Bytes: %s" % (file_path, file_size))
    except (IndexError, TypeError):
        file_size = None
        print("Downloading: %s Bytes: %s" % (file_path, "Unknown"))

    # Download with progress bar
    #
    file_size_dl = 0
    block_sz = 8192
    while True:
        buffer = u.read(block_sz)
        if not buffer:
            break

        file_size_dl += len(buffer)
        f.write(buffer)
        if file_size is not None:
            status = "\r%10d  [%3.2f%%]" % (file_size_dl, file_size_dl * 100. / file_size)
            if PY3:
                exec("print(status, end='\\r')", {"status": status})
            else:
                exec("print status, ", {"status": status})

    f.close()
    return file_path


def winapi_path(dos_path, encoding=None):
    path = os.path.abspath(dos_path)

    if path.startswith("\\\\?\\"):
        pass
    elif path.startswith("\\\\"):
        path = "\\\\?\\UNC\\" + path[2:]
    else:
        path = "\\\\?\\" + path

    return path


path_fix = winapi_path if IS_WIN else lambda path: path


class ZipfileLongPaths(zipfile.ZipFile):

    def _extract_member(self, member, targetpath, pwd):
        targetpath = winapi_path(targetpath)
        return zipfile.ZipFile._extract_member(self, member, targetpath, pwd)


_ZipFile = ZipfileLongPaths if IS_WIN else zipfile.ZipFile


def open_archive(file_path, dont_extract=None):
    """Extract archive file (zip/tar) in current working dir

    Archive will firstly temporally extract into `./extract_dir`, and
    move extracted content into `root_dir`.

    A flag file named `EXTRACTED` will be created in `./extract_dir`, this
    is for avoid re-extract same content when running build script.

    """
    # Open the archive and retrieve the name of the top-most directory.
    # This assumes the archive contains a single directory with all
    # of the contents beneath it.
    try:
        if tarfile.is_tarfile(file_path):
            archive = tarfile.open(file_path)
            members = archive.getmembers()

            if dont_extract is not None:
                members = [m for m in members
                           if not any((fnmatch.fnmatch(m.name, p)
                                       for p in dont_extract))]

            if not PY3:
                for m in members:
                    m.name = m.name.decode("utf-8")

            root_dir = [m.name for m in members][0].split('/')[0]

        elif zipfile.is_zipfile(file_path):
            archive = _ZipFile(file_path)
            members = archive.namelist()

            if dont_extract is not None:
                members = (m for m in members
                           if not any((fnmatch.fnmatch(m, p)
                                       for p in dont_extract)))
                members = list(members)

            root_dir = members[0].split('/')[0]

        else:
            raise RuntimeError("unrecognized archive file type")

        with archive:
            tmp_extracted_path = os.path.abspath("extract_dir")
            extracted_path = os.path.abspath(root_dir)
            extracted_flag = os.path.join(tmp_extracted_path, "EXTRACTED")

            if (os.path.isdir(extracted_path)
                    and os.path.isfile(extracted_flag)):
                print("Extracted flag found, skip extract. Remove flag file "
                      "to re-extract if needed:\n\t%s"
                      % extracted_flag)

                return extracted_path

            if os.path.isdir(extracted_path):
                print("Cleaning previous extract: %s" % extracted_path)
                clean(extracted_path)
                os.rmdir(extracted_path)

            print("Extracting archive to %s" % extracted_path)
            # Extract to a temporary directory then move the contents
            # to the expected location when complete. This ensures that
            # incomplete extracts will be retried if the script is run
            # again.
            if os.path.isdir(tmp_extracted_path):
                clean(tmp_extracted_path)

            archive.extractall(tmp_extracted_path, members=members)

            shutil.move(os.path.join(tmp_extracted_path, root_dir),
                        extracted_path)
            clean(tmp_extracted_path)
            # put extracted flag
            open(extracted_flag, "w").close()

            return extracted_path

    except Exception as e:
        raise RuntimeError("Failed to extract archive {filename}: {err}"
                           .format(filename=file_path, err=e))


@contextlib.contextmanager
def working_dir(path):
    cwd = os.getcwd()
    if not os.path.isdir(path):
        os.makedirs(path)
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(cwd)


def is_debug_build():
    return "release-0" in (os.environ["REZ_BUILD_VARIANT_REQUIRES"]
                           # Dependent package's build variant
                           + os.getenv("REZ_DEP_BUILD_VARIANTS", ""))


def run_cmake(source, install, extra_args=None, build_type=None):
    if build_type is None:
        build_type = "Debug" if is_debug_build() else "Release"

    config = shlex.split(
        "cmake "
        "-G \"{generator}\" "
        "-DCMAKE_INSTALL_PREFIX=\"{install}\" "
        "-DCMAKE_BUILD_TYPE={build_type} "
        "{extra_args} "
        "\"{source}\""
        .format(install=install,
                build_type=build_type,
                generator=os.environ["REZ_CMAKE_GENERATOR"],
                extra_args=" ".join(extra_args) if extra_args else "",
                source=source)
    )
    build = shlex.split(
        "cmake "
        "--build . "
        "--config {build_type} "
        "--target install "
        .format(build_type=build_type)
    )
    subprocess.check_call(config)
    subprocess.check_call(build)


clean = _rezbuild.clean
tell = _rezbuild.tell


def clear_build(path):
    """Deprecated, use `rez-build --clean` instead"""
    if os.path.exists(path):
        tell("Cleaning previous build..", 3)
        clean(path)


def patch_file(fname, patches, multiline_matches=False):
    """Applies patches to the specified file. patches is a list of tuples
        (old string, new string).
    """
    if multiline_matches:
        old_lines = [open(fname, "r").read()]
    else:
        old_lines = open(fname, "r").readlines()

    newLines = old_lines
    for (oldString, newString) in patches:
        newLines = [s.replace(oldString, newString) for s in newLines]

    if newLines != old_lines:
        tell("Patching file {filename} (original in {oldFilename})..."
             .format(filename=fname, oldFilename=fname + ".old"))

        shutil.copy(fname, fname + ".old")
        open(fname, "w").writelines(newLines)


def copy_files(src, dest):
    files = glob.glob(src)
    if not files:
        raise RuntimeError("File(s) to copy not found: %s" % src)

    # Ensure destination folder is created
    if not os.path.exists(dest):
        os.makedirs(dest)

    for src_file in files:
        # Explicitly copy to file destination
        dest_file = os.path.join(dest, os.path.basename(src_file))
        print("Copying %s -> %s" % (src_file, dest_file))
        shutil.copyfile(src_file, dest_file)


def copy_dir(src, dest):
    if os.path.isdir(dest):
        clean(dest)
        os.rmdir(dest)

    print("Copying %s -> %s" % (src, dest))
    shutil.copytree(src, dest)


def merge_dir(src, dst):
    if not os.path.isdir(src):
        return

    for root, dirs, fnames in os.walk(src):
        sub_path = os.path.relpath(root, src)
        for fname in fnames:
            src_file = os.path.join(root, fname)
            dst_dir = os.path.join(dst, sub_path)
            dst_file = os.path.join(dst_dir, fname)

            print("Copying %s -> %s" % (src_file, dst_file))
            if not os.path.isdir(dst_dir):
                os.makedirs(dst_dir)

            shutil.copyfile(src_file, dst_file)


def python_info():
    """Returns a tuple containing the path to the Python executable, shared
    library, and include directory corresponding to the version of Python
    currently running. Returns None if any path could not be determined.
    This function is used to extract build information from the Python
    interpreter used to launch this script. This information is used
    in the Boost and USD builds. By taking this approach we can support
    having USD builds for different Python versions built on the same
    machine. This is very useful, especially when developers have multiple
    versions installed on their machine, which is quite common now with
    Python2 and Python3 co-existing.

    # Modified from Pixar USD build script
    # https://github.com/PixarAnimationStudios/USD/blob/release/build_scripts/
    # build_usd.py

    """
    import os
    import sys
    import sysconfig

    # First we extract the information that can be uniformly dealt with across
    # the platforms:
    pythonExecPath = sys.executable
    pythonVersion = sysconfig.get_config_var("py_version_short")  # "2.7"
    pythonVersionNoDot = sysconfig.get_config_var("py_version_nodot")  # "27"

    # Lib path is unfortunately special for each platform and there is no
    # config_var for it. But we can deduce it for each platform, and this
    # logic works for any Python version.
    def _GetPythonLibraryFilename():
        if IS_WIN:
            return "python" + pythonVersionNoDot + ".lib"
        elif IS_LNX:
            return sysconfig.get_config_var("LDLIBRARY")
        elif IS_MAC:
            return "libpython" + pythonVersion + ".dylib"
        else:
            raise RuntimeError("Platform not supported")

    pythonIncludeDir = sysconfig.get_config_var("INCLUDEPY")

    if IS_WIN:
        pythonBaseDir = sysconfig.get_config_var("base")
        pythonLibPath = os.path.join(pythonBaseDir, "libs",
                                     _GetPythonLibraryFilename())

    elif IS_LNX:
        pythonLibDir = sysconfig.get_config_var("LIBDIR")
        pythonMultiarchSubdir = sysconfig.get_config_var("multiarchsubdir")
        if pythonMultiarchSubdir:
            pythonLibDir = pythonLibDir + pythonMultiarchSubdir
        pythonLibPath = os.path.join(pythonLibDir,
                                     _GetPythonLibraryFilename())

    elif IS_MAC:
        pythonBaseDir = sysconfig.get_config_var("base")
        pythonLibPath = os.path.join(pythonBaseDir, "lib",
                                     _GetPythonLibraryFilename())

    else:
        raise RuntimeError("Platform not supported")

    return pythonExecPath, pythonLibPath, pythonIncludeDir, pythonVersion
