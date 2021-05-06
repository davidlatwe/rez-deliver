
import os
import unittest

from rez.utils.sourcecode import _add_decorator, SourceCode, late
from rez.package_repository import package_repository_manager
from rez.config import config, _create_locked_config
from rez.package_serialise import dump_package_data
from rez.serialise import process_python_objects
from rez.package_maker import PackageMaker
from rez.serialise import FileFormat


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

    def add(self, name, **kwargs):
        data = kwargs
        data["name"] = name

        # process early/late bound functions
        #
        for key, value in kwargs.items():
            if hasattr(value, "_early"):
                kwargs[key] = SourceCode(func=value, eval_as_function=True)
        process_python_objects(data)

        # write out
        #
        pkg_base_path = os.path.join(self._path, name)
        version = data.get("version")
        if version and isinstance(version, str):
            pkg_base_path = os.path.join(pkg_base_path, version)

        filepath = os.path.join(pkg_base_path, "package.py")
        os.makedirs(pkg_base_path, exist_ok=True)
        with open(filepath, "w") as f:
            dump_package_data(data, buf=f, format_=FileFormat.py)

        # For debug
        #
        # with open(filepath, "r") as f:
        #     print(f.read())


def early():
    def decorated(fn):
        setattr(fn, "_early", True)
        _add_decorator(fn, "early")
        return fn

    return decorated
