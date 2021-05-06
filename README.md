# rez-deliver

Rez CLI/GUI tool for installing packages from developer package repositories.


### What is this for ?

Simply put, this project is a implementation of [REP-002](https://github.com/nerdvegas/rez/issues/673).011, which is aiming for building packages from one or more developer package repositories and most importantly, auto resolve the dependencies of each requested package for installation.


### Requirement

* Python 3.4+
* Rez

Currently this is still in development, and require un-merged PRs in [nerdvegas/rez](https://github.com/nerdvegas/rez):

* [nerdvegas/rez#1040](https://github.com/nerdvegas/rez/pull/1040) for command plugin interface.
* [nerdvegas/rez#1060](https://github.com/nerdvegas/rez/pull/1060) for testing directive request (Not a must).


### Installation

With [nerdvegas/rez#1040](https://github.com/nerdvegas/rez/pull/1040), install with rez venv's pip should work.

```shell
$ git clone https://github.com/davidlatwe/rez-deliver.git
$ cd /path/to/rez-deliver
$ rez-python -m pip install .
```

`PySide2` or `PyQt5` is required for GUI mode.


### Usage

Setup your developer repository by rezconfig.

```python
# rezconfig
plugins = {
    "command": {
        "deliver": {
            "dev_repository_roots": [
                # developer repository path here
            ],
}}}
```

And see helps.

```shell
$ rez deliver -h
```


### Developer Package Repository

A Rez developer package repository should just looks like any regular filesystem-based package repository, but without the structure of variation which contains built/variated package payloads.


### Developer package

Here is a list about different kinds of developer package on how payload should be accessed during build, and how versions are being managed:

* version per dir
* version per git tag
* payload included
* payload separated
    - From git (source)
    - From archive (prebuilt binaries)
* payload existed
    - bind
    - reference

Payloads that are versioned with git can be handled and retrieved by build script, but listing all versions from one package definition file as installation option is trickier.

Current approach is to use `git ls-remote --tags <url>` for fetching tags and re-evaluate same package.py file for each tag to generate versions of package. See the following example:

```python
# package.py

git_url = "https://github.com/davidlatwe/delivertest.git"

@early()
def version():
    import os

    package_ver = "p1"
    payload_ver = os.getenv("REZ_DELIVER_PKG_PAYLOAD_VER")

    if payload_ver:
        return "%s-%s" % (payload_ver, package_ver)
    else:
        return "0.0.0-" + package_ver
```

The environment var `REZ_DELIVER_PKG_PAYLOAD_VER` is provided from `rez-deliver`, if the package has the attribute `git_url`.


### Contribute

Welcome to submit issue or pull request.
