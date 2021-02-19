
import os as __os

dev_repository_root = "~/pipeline/rez-deliver/test"

rez_source_path = "~/pipeline/rez"

with open(__os.path.expanduser("~/github.token"), "r") as f:
    github_token = f.read().strip()

# Rez package release destinations
deliver_targets = [
    # name: target name
    # template: package install/release path template
    # source: JSON that contains key-values for template keyword formatting
    {
        "name": "user",
        "description": "user beta",
        "template": "T:/rez-studio/packages/1/beta-user/{user}",
        "source": "T:/rez-studio/deploy/data/targets.json",
    },
    {
        "name": "dept",
        "description": "department beta",
        "template": "T:/rez-studio/packages/1/beta-dept/{department}",
        "source": "T:/rez-studio/deploy/data/targets.json",
    },
    {
        "name": "site",
        "description": "site-wide release",
        "template": "T:/rez-studio/packages/1/release",
        "source": None,
    },
]

# Cache dev packages into a JSON file for quicker startup on next launch.
cache_dev_packages = False

# Auto update dev packages cache after given days
dev_packages_cache_days = 7
