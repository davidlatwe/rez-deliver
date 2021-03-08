
from rez.config import PathList, Str


class AppDeliver(object):

    schema_dict = {
        "dev_repository_roots": PathList,
        "rez_source_path": Str,
        "github_token": Str,
        "cache_dev_packages": bool,
        "dev_packages_cache_days": int,
    }

    @classmethod
    def name(cls):
        return "deliver"


def register_plugin():
    return AppDeliver
