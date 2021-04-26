

name = "delivertest"

git_url = "https://github.com/davidlatwe/delivertest.git"


@early()
def version():
    import os

    package_ver = "m1"
    payload_ver = os.getenv("REZ_DELIVER_PKG_PAYLOAD_VER")

    if payload_ver:
        return "%s-%s" % (
            # payload version
            payload_ver,
            # package def version
            package_ver
        )

    else:
        return "0.0.0-" + package_ver


def pre_build_commands():
    env = globals()["env"]
    expandvars = globals()["expandvars"]
    optionvars = globals()["optionvars"]

    feature = expandvars("{this.name}.dev")
    env.REZ_BUILD_PKG_PAYLOAD_ROOT = optionvars(feature, default="")


requires = []

private_build_requires = ["rezutil-1"]
build_command = "python {root}/rezbuild.py {install}"


def pre_commands():
    this = globals()["this"]
    stop = globals()["stop"]
    expandvars = globals()["expandvars"]
    intersects = globals()["intersects"]
    ephemerals = globals()["ephemerals"]
    optionvars = globals()["optionvars"]

    # Change package root to dev repo
    feature = expandvars("{this.name}.dev")
    default = "%s-0" % feature
    if intersects(ephemerals.get(feature, default), "1"):
        # Change payload path
        # Must use {this.root} instead of {root} in path
        dev_root = optionvars(feature)
        if dev_root:
            this.root = dev_root
        else:
            stop("%s not set in rezconfig.." % feature)


def commands():
    env = globals()["env"]
    env.PATH.prepend("{this.root}/payload/bin")
