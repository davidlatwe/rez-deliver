
import os
import sys
import unittest
from contextlib import contextmanager

from rez.plugin_managers import plugin_manager, PackageRepositoryPluginType
from rez.utils.sourcecode import _add_decorator, SourceCode, late
from rez.package_repository import package_repository_manager
from rez.package_maker import PackageMaker, package_schema
from rez.package_resources import package_pod_schema
from rez.config import config, _create_locked_config
from rez.serialise import process_python_objects
from rez.vendor.schema.schema import Or
from rez.serialise import FileFormat
from rez.package_serialise import (
    package_serialise_schema,
    dump_package_data,
)


__all__ = [
    "TestBase",
    "MemoryPkgRepo",
    "DeveloperPkgRepo",
    "early",
    "late",
]


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


class PkgRepo(object):
    def __init__(self, path):
        self._path = path

    @property
    def path(self):
        return self._path


class MemoryPkgRepo(PkgRepo):

    def __init__(self, ident):
        super(MemoryPkgRepo, self).__init__("memory@" + ident)
        self._repo = package_repository_manager.get_repository(self._path)

    def add(self, name, **kwargs):
        maker = PackageMaker(name, data=kwargs)
        package = maker.get_package()
        data = package.data
        version = data.get("version", "_NO_VERSION")

        mem_data = self._repo.data
        if name not in mem_data:
            mem_data[name] = dict()
        mem_data[name].update({version: data})


class DeveloperPkgRepo(PkgRepo):
    """A repository that able to read/write developer packages"""

    def __init__(self, path):
        super(DeveloperPkgRepo, self).__init__(path=path)
        self._out_early_enabled = False

    @contextmanager
    def enable_out_early(self):
        schema_objects = [
            package_schema,
            package_pod_schema,
            package_serialise_schema,
        ]
        originals = list()

        for schema_obj in schema_objects:
            originals.append(schema_obj._schema)
            # make every attribute early-able
            schema_obj._schema = {
                k: Or(SourceCode, v)  # just like what `late_bound` does
                for k, v in schema_obj._schema.items()
            }

        self._out_early_enabled = True

        yield

        for i, schema_obj in enumerate(schema_objects):
            schema_obj._schema = originals[i]

        # repository plugins must be resetted to reload schemas
        _reset_package_repository_plugin()
        self._out_early_enabled = False

    def add(self, name, **kwargs):
        if self._out_early_enabled:
            # process early bound functions
            for key, value in kwargs.items():
                if hasattr(value, "_early"):
                    kwargs[key] = SourceCode(func=value,
                                             eval_as_function=True)

        maker = PackageMaker(name, data=kwargs)
        package = maker.get_package()
        data = package.data
        version = data.get("version")

        if version and isinstance(version, str):
            pkg_base_path = os.path.join(self._path, name, version)
        else:
            # no version or early bounded
            pkg_base_path = os.path.join(self._path, name)

        process_python_objects(data)

        filepath = os.path.join(pkg_base_path, "package.py")
        os.makedirs(pkg_base_path, exist_ok=True)
        with open(filepath, "w") as f:
            dump_package_data(data, buf=f, format_=FileFormat.py)


def early():
    def decorated(fn):
        setattr(fn, "_early", True)
        _add_decorator(fn, "early")
        return fn

    return decorated


def _reset_package_repository_plugin():
    package_repository_manager.clear_caches()
    package_repository_manager.pool.resource_classes.clear()

    plugin_manager.register_plugin_type(PackageRepositoryPluginType)

    for key in list(sys.modules.keys()):
        if key.startswith("rezplugins.package_repository"):
            del sys.modules[key]
