
name = "rezutil"

version = "1.4.6-m1"

build_command = "python {root}/rezbuild.py {install}"


def commands():
    env = globals()["env"]
    env.PYTHONPATH.prepend("{root}/python")
