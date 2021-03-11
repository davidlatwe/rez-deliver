
import os as __os
__root = __os.path.dirname(__file__) + "/../.."

with open(__os.path.expanduser("~/github.token"), "r") as f:
    __github_token = f.read().strip()

deliver = {
    "dev_repository_roots": [
        __os.path.join(__root, "test", "packages"),
        __os.path.join(__root, "test", "others"),
    ],

    "rez_source_path": "~/pipeline/rez",

    "github_token": __github_token,

    # Cache dev packages into a JSON file for quicker startup on next launch.
    "cache_dev_packages": False,

    # Auto update dev packages cache after given days
    "dev_packages_cache_days": 7,
}
