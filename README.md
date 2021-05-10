# rez-deliver

Rez CLI/GUI tool for installing packages from developer package repositories.


### What is this for ?

Simply put, this project is a implementation of [REP-002](https://github.com/nerdvegas/rez/issues/673).011, which is aiming for building packages from one or more developer package repositories and most importantly, auto resolve the dependencies of each requested package for installation.


### Requirement

* Python 3.4+
* Rez
* Python Qt5 binding for GUI mode

### Installation

Best to install with [rezup](https://github.com/davidlatwe/rezup), it will take care Rez production standard entrypoints:

1. Saving these into `~/rezup.toml`
    
    ```toml
    description = "rezup container revision recipe"
    
    [rez]
    url = "rez"
    
    [[extension]]
    name = "rez-deliver"
    url = "git+git://github.com/davidlatwe/rez-deliver[gui]"
    ```

2. In terminal

    ```shell
    $ pip install rezup
    $ rezup use --make
    $ rez-deliver -h
    ```

Now, if you DO NOT have [nerdvegas/rez#1040](https://github.com/nerdvegas/rez/pull/1040) merged, one extra step is :

```python
# rezconfig.py
plugin_path = ModifyList(append=[
    # The path *above* rezplugins/ directory
    "/path/to/rez-deliver/src/deliver",
])
```


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
