
import os
import sys
from .vendor.Qt5 import QtCore, QtWidgets
from ..cli import load_userconfig as _load_userconfig
from . import resources, control, app


def init():
    if sys.platform == "darwin":
        os.environ["QT_MAC_WANTS_LAYER"] = "1"  # MacOS BigSur

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    storage = QtCore.QSettings(QtCore.QSettings.IniFormat,
                               QtCore.QSettings.UserScope,
                               "Sweet", "preferences")
    print("Preference file: %s" % storage.fileName())

    try:
        _load_userconfig()
    except IOError:
        pass

    resources.load_themes()
    qss = resources.load_theme(name=storage.value("theme"))

    ctrl = control.Controller(storage)
    window = app.Window(ctrl=ctrl)
    window.setStyleSheet(qss)

    return qapp, window, ctrl


def main():
    qapp, window, ctrl = init()
    window.show()

    ctrl.defer_search_packages(on_time=200)

    return qapp.exec_()
