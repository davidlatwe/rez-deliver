
import os
import sys
from .vendor.Qt5 import QtCore, QtWidgets
from . import view, resources, control


APP_NAME = "Deliver"


class Window(QtWidgets.QWidget):

    def __init__(self, ctrl, parent=None):
        super(Window, self).__init__(parent=parent)

        pages = {
            "pkgBook": view.PackageBookView(),
            "split": QtWidgets.QSplitter(),
            "actions": QtWidgets.QTabWidget(),
            "pkgInfo": view.PackageDataView(),
            "install": view.InstallerView(),
        }

        pages["actions"].addTab(pages["pkgInfo"], "Package")
        pages["actions"].addTab(pages["install"], "Install")

        pages["split"].setOrientation(QtCore.Qt.Horizontal)
        pages["split"].addWidget(pages["pkgBook"])
        pages["split"].addWidget(pages["actions"])

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(pages["split"])

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
        if pkg_name:
            is_variant = variant_index >= 0
            package = self._ctrl.find_dev_package(pkg_name)
        else:
            is_variant = False
            package = None

        self._pages["pkgInfo"].parse_package(package, is_variant)


def init():
    if sys.platform == "darwin":
        os.environ["QT_MAC_WANTS_LAYER"] = "1"  # MacOS BigSur

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    storage = QtCore.QSettings(QtCore.QSettings.IniFormat,
                               QtCore.QSettings.UserScope,
                               APP_NAME, "preferences")
    print("Preference file: %s" % storage.fileName())

    resources.load_themes()
    qss = resources.load_theme(name=storage.value("theme"))

    ctrl = control.Controller(storage)
    window = Window(ctrl=ctrl)
    window.setStyleSheet(qss)

    return qapp, window, ctrl


def main():
    qapp, window, ctrl = init()
    window.show()

    ctrl.defer_search_packages(on_time=200)

    return qapp.exec_()
