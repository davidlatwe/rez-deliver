
from .vendor.Qt5 import QtWidgets
from . import view


class Window(QtWidgets.QWidget):

    def __init__(self, ctrl, parent=None):
        super(Window, self).__init__(parent=parent)

        pages = {
            "pkgBook": view.PackageBookView(),
            "actions": QtWidgets.QTabWidget(),
            "pkgInfo": view.PackageDataView(),
            "install": view.InstallerView(),
        }

        pages["actions"].addTab(pages["pkgInfo"], "Package")
        pages["actions"].addTab(pages["install"], "Install")

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(pages["pkgBook"])
        layout.addWidget(pages["actions"])

        # setup
        pages["pkgBook"].set_model(ctrl.models["pkgBook"])
        pages["install"].set_model(ctrl.models["pkgPaths"],
                                   ctrl.models["pkgManifest"])

        # signals
        pages["pkgBook"].selected.connect(self.on_package_selected)
        pages["install"].targeted.connect(ctrl.on_target_changed)
        pages["install"].manifested.connect(ctrl.on_manifested)
        pages["install"].installed.connect(ctrl.on_installed)

        self._ctrl = ctrl
        self._pages = pages

        self.init()

    def init(self):
        self._pages["install"].init()

    def on_package_selected(self, pkg_name, variant_index):
        is_variant = variant_index >= 0
        package = self._ctrl.find_dev_package(pkg_name)
        self._pages["pkgInfo"].parse_package(package, is_variant)
