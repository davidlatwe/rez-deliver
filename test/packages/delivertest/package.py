

name = "delivertest"

github_repo = "davidlatwe/delivertest"  # for rez-deliver


@early()
def version():
    import os

    package_ver = "m1"

    # These two environment variables should be set by our
    # 'github-based Rez package releasing tool' -> rez-deliver
    #
    payload_ver = "REZ_DELIVER_PKG_PAYLOAD_VER"

    if os.getenv(payload_ver):
        return "%s-%s" % (
            # payload version
            os.environ[payload_ver],
            # package def version
            package_ver
        )

    else:
        return "0.0.0-" + package_ver


def pre_build_commands():
    env = globals()["env"]
    this = globals()["this"]
    env.GITHUB_REPO = this.github_repo


requires = []

private_build_requires = ["rezutil-1"]
build_command = "python {root}/rezbuild.py {install}"


@late()
def dev_paths():
    # Load dev path from JSON
    return {
        "root": "C:/Users/david/rez/packages/install/foo/1/dev",
        "bin": None,
    }


def pre_commands():
    this = globals()["this"]
    expandvars = globals()["expandvars"]
    intersects = globals()["intersects"]
    ephemerals = globals()["ephemerals"]

    # Change package root to dev repo
    feature = expandvars("{this.name}.dev")
    default = "%s-0" % feature
    if intersects(ephemerals.get(feature, default), "1"):
        # Must using {this.root} instead of {root} in path
        this.root = "C:/Users/david/rez/packages/install/foo/1/dev"


def commands():
    env = globals()["env"]
    env.PATH.prepend("{this.root}/payload/bin")
