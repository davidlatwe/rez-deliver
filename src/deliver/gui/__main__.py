
from Qt5 import QtWidgets
from . import view, control


def show():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    ctrl = control.Controller()
    window = view.Window(ctrl=ctrl)
    window.show()

    ctrl.defer_search_packages(on_time=200)

    app.exec_()


show()
