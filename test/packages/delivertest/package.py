

name = "delivertest"

github_repo = "davidlatwe/delivertest"  # for rez-deliver


@early()
def version():
    import os

    # These two environment variables should be set by our
    # 'github-based Rez package releasing tool' -> rez-deliver
    #
    payload_ver = "GITHUB_REZ_PKG_PAYLOAD_VER"

    if os.getenv(payload_ver):
        return "%s-%s" % (
            # payload version
            os.environ[payload_ver],
            # package def version
            "m1"
        )

    else:
        return "0.0.0-m0"


def pre_build_commands():
    env = globals()["env"]
    this = globals()["this"]
    env.GITHUB_REPO = this.github_repo


requires = []

private_build_requires = ["rezutil-1"]
build_command = "python {root}/rezbuild.py {install}"


def commands():
    env = globals()["env"]
    env.PATH.prepend("{root}/payload/bin")
