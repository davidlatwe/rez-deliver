from __future__ import print_function, with_statement

import os
import sys
import fnmatch
from setuptools import setup, find_packages


# carefully import some sourcefiles that are standalone
source_path = os.path.dirname(os.path.realpath(__file__))
src_path = os.path.join(source_path, "src")
sys.path.insert(0, src_path)

from deliver._version import version


def find_files(pattern, path=None, root="deliver", prefix=""):
    paths = []
    basepath = os.path.realpath(os.path.join("src", root))
    path_ = basepath
    if path:
        path_ = os.path.join(path_, path)

    for root, _, files in os.walk(path_):
        files = [x for x in files if fnmatch.fnmatch(x, pattern)]
        files = [os.path.join(root, x) for x in files]
        paths += [x[len(basepath):].lstrip(os.path.sep) for x in files]

    return [prefix + p for p in paths]


with open(os.path.join(source_path, "README.md")) as f:
    long_description = f.read()


setup(
    name="rez-deliver",
    package_data={
        "deliver":
            find_files("rezconfig") +
            find_files("*.ttf", "gui/resources/fonts") +
            find_files("*.svg", "gui/resources/images") +
            find_files("*.svg", "gui/resources/images") +
            find_files("*.png", "gui/resources/images") +
            find_files("*.qss", "gui/resources") +
            find_files("LICENSE.*") +
            find_files("LICENSE")
    },
    install_requires=[
        "pygithub",
        "requests==2.24.0",
    ],
    extras_require={
        "gui":  ["qt5.py", "pyside2"],
    },
    packages=find_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    zip_safe=False,
    license="LGPL",
    author="davidlatwe",
    author_email="davidlatwe@gmail.com",
    version=version,
    description="Rez cli for releasing packages from GitHub repositories",
    long_description=long_description,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Software Development",
        "Topic :: System :: Software Distribution"
    ],
)
