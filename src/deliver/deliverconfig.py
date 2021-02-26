
import os as __os

dev_repository_roots = [
    "~/pipeline/rez-deliver/test/packages",
]

rez_source_path = "~/pipeline/rez"

with open(__os.path.expanduser("~/github.token"), "r") as f:
    github_token = f.read().strip()


# Cache dev packages into a JSON file for quicker startup on next launch.
cache_dev_packages = False

# Auto update dev packages cache after given days
dev_packages_cache_days = 7
