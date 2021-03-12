
import os as __os
__root = __os.path.join(__os.path.dirname(__file__), *[".."] * 4)


def _github_token():
    with open(__os.path.expanduser("~/github.token"), "r") as f:
        return f.read().strip()


# CONFIG
deliver = {
    "dev_repository_roots": [
        __os.path.join(__root, "test", "packages"),
        __os.path.join(__root, "test", "others"),
    ],

    "rez_source_path": "~/pipeline/rez",

    "github_token": _github_token(),

    # Cache dev packages into a JSON file for quicker startup on next launch.
    "cache_dev_packages": False,

    # Auto update dev packages cache after given days
    "dev_packages_cache_days": 7,
}
