
__version__ = "0.2.0"


def package_info():
    import deliver
    return dict(
        name=deliver.__package__,
        version=__version__,
        path=deliver.__path__[0],
    )


def print_info():
    import sys
    info = package_info()
    py = sys.version_info
    print(info["name"],
          info["version"],
          "from", info["path"],
          "(python {x}.{y})".format(x=py.major, y=py.minor))
