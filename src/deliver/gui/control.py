
from rez.packages import iter_package_families, get_latest_package_from_string
from .vendor.Qt5 import QtCore
from . import model, common
from .. import pkgs
from ..config import config


class State(dict):

    def __init__(self, storage):
        dev_repo = pkgs.DevPkgManager()
        installer = pkgs.PackageInstaller(dev_repo)

        super(State, self).__init__({
            "devRepoRoot": dev_repo,
            "installer": installer,
            "releaseTarget": None,
        })

        self._storage = storage

    def store(self, key, value):
        """Write to persistent storage

        Arguments:
            key (str): Name of variable
            value (object): Any datatype

        """
        self[key] = value
        self._storage.setValue(key, value)

    def retrieve(self, key, default=None):
        """Read from persistent storage

        Arguments:
            key (str): Name of variable
            default (any): default value if key not found

        """
        value = self._storage.value(key)

        if value is None:
            value = default

        # Account for poor serialisation format
        true = ["2", "1", "true", True, 1, 2]
        false = ["0", "false", False, 0]

        if value in true:
            value = True

        if value in false:
            value = False

        if value and str(value).isnumeric():
            value = float(value)

        return value


class Controller(QtCore.QObject):

    def __init__(self, storage=None, parent=None):
        super(Controller, self).__init__(parent=parent)

        state = State(storage=storage)

        timers = {
            "packageSearch": QtCore.QTimer(self),
            "targetsLoad": QtCore.QTimer(self),
            "targetKeysLoad": QtCore.QTimer(self),
        }

        models_ = {
            "pkgBook": model.PackageBookModel(),
            "pkgData": common.model.JsonModel(),
            "pkgDep": None,
            "targets": QtCore.QStringListModel(),
            "pathKeys": model.StringFormatModel(),
            "detail": common.model.JsonModel(),
        }

        timers["packageSearch"].timeout.connect(self.on_package_searched)
        timers["targetsLoad"].timeout.connect(self.on_target_loaded)
        timers["targetKeysLoad"].timeout.connect(self.on_target_keys_loaded)

        self._state = state
        self._timers = timers
        self._models = models_

    @property
    def state(self):  # state is also like a model and good to be exposed
        return self._state

    @property
    def models(self):
        return self._models

    def defer_search_packages(self, on_time=50):
        timer = self._timers["packageSearch"]
        timer.setSingleShot(True)
        timer.start(on_time)

    def defer_load_targets(self, on_time=50):
        timer = self._timers["targetsLoad"]
        timer.setSingleShot(True)
        timer.start(on_time)

    def defer_load_target_keys(self, name, on_time=50):
        self._state["releaseTarget"] = name
        timer = self._timers["targetKeysLoad"]
        timer.setSingleShot(True)
        timer.start(on_time)

    def on_package_searched(self):
        self._state["devRepoRoot"].reload()
        self._models["pkgBook"].reset(self.iter_dev_packages())

    def on_target_loaded(self):
        targets = [t["name"] for t in config.release_targets]
        self._models["targets"].setStringList(targets)

    def on_target_keys_loaded(self):
        target = self._state["releaseTarget"]
        param = config.release_target_param

        self._models["pathKeys"].load({
            key: param[key]
            for key in config.list_target_required_keys(target)
        })

        self._models["pathKeys"].formatted.emit()

    def on_package_selected(self, name, index):
        if name:
            package = self.find_dev_package(name)
            # is_variant = index >= 0
            #
            # if is_variant:
            #     variant = package.get_variant(index)

            data = package.data.copy()
            self._models["detail"].load(data)

            # TODO: This should be called when package is checked
            installer = self._state["installer"]
            installer.resolve(name)

        else:
            self._models["detail"].clear()

    def on_installed(self):
        installer = self._state["installer"]
        print(installer.manifest())

    def iter_dev_packages(self):
        paths = [self._state["devRepoRoot"].uri()]
        seen = dict()

        for family in iter_package_families(paths=paths):
            name = family.name
            path = family.resource.location

            for package in family.iter_packages():
                qualified_name = package.qualified_name

                if qualified_name in seen:
                    seen[qualified_name]["locations"].append(path)
                    continue

                doc = {
                    "family": name,
                    "version": str(package.version),
                    "uri": package.uri,
                    "tools": package.tools or [],
                    "qualified_name": qualified_name,
                    "locations": [path],
                    "numVariants": package.num_variants,
                }
                seen[qualified_name] = doc

                yield doc

    def find_dev_package(self, name):
        paths = [self._state["devRepoRoot"].uri()]
        package = get_latest_package_from_string(name, paths=paths)
        return package
