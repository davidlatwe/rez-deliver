
import os
import unittest
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
