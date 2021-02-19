
import os
import functools
from string import Formatter
from . import deliverconfig


def _expand_norm_path(path):
    path = functools.reduce(
        lambda _p, f: f(_p),
        [path,
         os.path.expanduser,
         os.path.expandvars,
         os.path.normpath]
    )

    return path


class Config(object):

    def __init__(self):
        self._release_targets = deliverconfig.release_targets()
        self._release_target_param = deliverconfig.release_target_param()
        self._validate_release_targets()

    @property
    def dev_repository_root(self):
        return _expand_norm_path(deliverconfig.dev_repository_root)

    @property
    def rez_source_path(self):
        return _expand_norm_path(deliverconfig.rez_source_path)

    @property
    def github_token(self):
        return deliverconfig.github_token

    @property
    def release_targets(self):
        return self._release_targets

    @property
    def release_target_param(self):
        return self._release_target_param

    @property
    def cache_dev_packages(self):
        return deliverconfig.cache_dev_packages

    @property
    def dev_packages_cache_days(self):
        return deliverconfig.dev_packages_cache_days

    def _validate_release_targets(self):
        assert self._release_targets, "No release target."

        for target in self._release_targets:
            path = target["template"]
            formatter = Formatter()
            for _, key, _, _ in formatter.parse(path):
                if key is None:
                    continue

                if key not in self._release_target_param:
                    raise RuntimeError(
                        "Key {%s} of path %r was not found in 'deliverconfig."
                        "release_target_param'." % (key, path)
                    )

    def list_target_required_keys(self, name):
        for target in self._release_targets:
            if target["name"] != name:
                continue

            return [
                key[1]
                for key in Formatter().parse(target["template"])
                if key[1] is not None
            ]

        raise RuntimeError("Unknown target: %s" % name)


config = Config()
