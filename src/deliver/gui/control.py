
from rez.config import config as rezconfig
from .vendor.Qt5 import QtCore
from . import model
from .. import pkgs


class State(dict):

    def __init__(self, storage):
        dev_repo = pkgs.DevRepoManager()
        installer = pkgs.PackageInstaller(dev_repo)

        super(State, self).__init__({
            "devRepoRoot": dev_repo,
            "installer": installer,
            "deployPaths": rezconfig.packages_path[:],
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
        }

        models_ = {
            "pkgBook": model.PackageBookModel(),
            "pkgPaths": QtCore.QStringListModel(state["deployPaths"]),
            "pkgManifest": model.PackageManifestModel(),
        }

        timers["packageSearch"].timeout.connect(self.on_package_searched)

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

    def on_package_searched(self):
        self._state["devRepoRoot"].load()
        self._models["pkgBook"].reset(self.iter_dev_packages())

    def on_target_changed(self, path):
        installer = self._state["installer"]
        installer.target(path)
        self._models["pkgManifest"].clear()

    def on_manifested(self):
        self.resolve_requests()
        installer = self._state["installer"]
        self._models["pkgManifest"].load(installer.manifest())

    def on_installed(self):
        # Unlike CLI mode that installer runs right after resolve, any package
        # change may happen e.g. deletion, after manifested in GUI mode. So we
        # re-resolve requests again here just in case.
        self.on_manifested()
        installer = self._state["installer"]
        for installed in installer.run_iter():
            qualified_name, variant_index = installed
            self._models["pkgManifest"].installed(qualified_name, variant_index)

    def iter_dev_packages(self):
        dev_repo = self._state["devRepoRoot"]
        seen = dict()

        for family in dev_repo.iter_package_families():
            name = family.name
            path = family.resource.location

            for package in family.iter_packages():
                if package.data.get("_DEV_SRC") == "_REZ_BIND":
                    break

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
        dev_repo = self._state["devRepoRoot"]
        return dev_repo.find(name)

    def resolve_requests(self):
        installer = self._state["installer"]
        installer.reset()
        for name, index in self._models["pkgBook"].iter_requests():
            installer.resolve(name, index)
