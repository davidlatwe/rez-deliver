

name = "delivertest"

version = "0.0.0-m0"

github_repo = "davidlatwe/delivertest"  # for rez-deliver


def preprocess(this, data):
    import os

    # These two environment variables should be set by our
    # 'github-based Rez package releasing tool' -> rez-deliver
    #
    payload_ver = "GITHUB_REZ_PKG_PAYLOAD_VER"
    release_path = "REZ_RELEASE_PACKAGES_PATH"

    if os.getenv(payload_ver):
        data["version"] = "%s-%s" % (
            # payload version
            os.environ[payload_ver],
            # package def version
            "m1"
        )

    if os.getenv(release_path):
        try:
            _ = data["config"]["release_packages_path"]
        except KeyError:
            data["config"] = data["config"] or {}
            data["config"]["release_packages_path"] = os.environ[release_path]
        else:
            pass  # already explicitly specified by package


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
