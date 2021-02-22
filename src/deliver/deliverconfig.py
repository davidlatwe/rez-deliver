
import os as __os

dev_repository_root = "~/pipeline/rez-deliver/test"

rez_source_path = "~/pipeline/rez"

with open(__os.path.expanduser("~/github.token"), "r") as f:
    github_token = f.read().strip()


def release_targets():
    """Rez package release destinations

    A list of dict that used to format package release path, the **first** in
    list is the default release target.

    {
        name: target-name (no space)
        description: release target description
        template: package install/release path template
    }

    """
    # from rez.config import config
    # return [
    #     {
    #         "name": "release",
    #         "description": "rez-release deploy path",
    #         "template": config.release_packages_path,
    #     },
    # ]

    return [
        {
            "name": "site",
            "description": "site-wide release",
            "template": "T:/rez-studio/packages/1/release",
        },
        {
            "name": "dept",
            "description": "department beta",
            "template": "T:/rez-studio/packages/1/beta-dept/{department}",
        },
        {
            "name": "user",
            "description": "user beta",
            "template": "T:/rez-studio/packages/1/beta-user/{user}",
        },
    ]


def release_target_param():
    """key-values for release target template keyword formatting"""
    import json
    with open("T:/rez-studio/deploy/data/targets.json", "rb") as fp:
        return json.load(fp)


# Cache dev packages into a JSON file for quicker startup on next launch.
cache_dev_packages = False

# Auto update dev packages cache after given days
dev_packages_cache_days = 7
