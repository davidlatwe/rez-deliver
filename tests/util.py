
import os
import unittest
import functools
from contextlib import contextmanager
from deliver.lib import temp_env
from rez.utils.yaml import save_yaml
from rez.config import config, _create_locked_config


class TestBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.settings = {}

    def setUp(self):
        # shield unit tests from any user config overrides
        self.setup_config()

    def tearDown(self):
        self.teardown_config()

    def setup_config(self):
        # to make sure config changes from one test don't affect another, copy
        # the overrides dict...
        self._config = _create_locked_config(dict(self.settings))
        config._swap(self._config)

    def teardown_config(self):
        # moved to it's own section because it's called in update_settings...
        # so if in the future, tearDown does more than call this,
        # update_settings is still valid
        config._swap(self._config)
        self._config = None

    @contextmanager
    def dump_config_yaml(self, dirpath):
        """Context that saves current testing config for e.g. subprocess"""
        filepath = os.path.join(dirpath, "rezconfig")

        data = config.validated_data()
        save_yaml(filepath, **data)

        with temp_env("REZ_CONFIG_FILE", filepath):
            yield

        os.remove(filepath)


try:
    from rez.utils import request_directives
except ImportError:
    __has_directives = False
else:
    __has_directives = True


def require_directives():
    """Decorator that skip test if rez doesn't have directives implemented"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if __has_directives:
                return func(self, *args, **kwargs)
            else:
                self.skipTest(
                    "Cannot test on rez that doesn't have REP-002 directives "
                    "implemented, skipping.."
                )

        return wrapper

    return decorator
