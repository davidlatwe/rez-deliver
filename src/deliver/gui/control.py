
from Qt5 import QtCore
from rez.packages import iter_package_families, get_latest_package_from_string
from .search.model import PackageModel
from .common.model import JsonModel
from ..pkgs import DevPkgRepository
from .. import git


ROOT = "C:/Users/davidlatwe.lai/pipeline/rez-kit"
# ROOT = "C:/Users/davidlatwe.lai/pipeline/rez-deliver/test"
REZ_SRC = "C:/Users/davidlatwe.lai/pipeline/rez"


class State(dict):

    def __init__(self, storage):
        super(State, self).__init__({
            "devRepoRoot": DevPkgRepository(ROOT),
            "currentGithubRepo": None,
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
    tag_fetched = QtCore.Signal(str, list)

    def __init__(self, storage=None, parent=None):
        super(Controller, self).__init__(parent=parent)

        state = State(storage=storage)

        timers = {
            "packageSearch": QtCore.QTimer(self),
            "releaseTagFetch": QtCore.QTimer(self),
        }

        models = {
            "package": PackageModel(),  # TODO: should rename to "repository"
            "detail": JsonModel(),
        }

        timers["packageSearch"].timeout.connect(self.on_package_searched)
        timers["releaseTagFetch"].timeout.connect(self.on_release_tag_fetched)

        self._state = state
        self._timers = timers
        self._models = models

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

    def defer_fetch_release_tag(self, on_time=200):
        timer = self._timers["releaseTagFetch"]
        timer.setSingleShot(True)
        timer.start(on_time)

    def on_package_searched(self):
        self._state["devRepoRoot"].reload()
        self._models["package"].reset(self.iter_dev_packages())

    def on_release_tag_fetched(self):
        github_repo = self._state["currentGithubRepo"]
        if github_repo:
            tags = list(git.get_released_tags(github_repo))
            self.tag_fetched.emit(github_repo, tags)

    def on_package_selected(self, name, index):
        package = self.find_dev_package(name)
        is_variant = index >= 0
        if is_variant:
            variant = package.get_variant(index)
            data = variant.data.copy()
        else:
            data = package.data.copy()

        self._models["detail"].load(data)

        github_repo = data.get("github_repo")
        current_repo = self._state["currentGithubRepo"]
        outdated = github_repo != current_repo
        if outdated:
            self._state["currentGithubRepo"] = github_repo
            self.defer_fetch_release_tag()

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
                    "timestamp": package.timestamp,
                    "locations": [path],
                    "numVariants": package.num_variants,
                }
                seen[qualified_name] = doc

                yield doc

    def find_dev_package(self, name):
        paths = [self._state["devRepoRoot"].uri()]
        package = get_latest_package_from_string(name, paths=paths)
        return package
