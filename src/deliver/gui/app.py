
from .vendor.Qt5 import QtWidgets
from . import view


class Window(QtWidgets.QWidget):

    def __init__(self, ctrl, parent=None):
        super(Window, self).__init__(parent=parent)

        pages = {
            "pkgBook": view.PackageBookView(),
            "installer": view.InstallerView(),
        }

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(pages["pkgBook"])
        layout.addWidget(pages["installer"])

        # setup
        pages["pkgBook"].set_model(ctrl.models["pkgBook"])
        pages["installer"].set_model(ctrl.models["detail"])

        # signals
        pages["pkgBook"].selected.connect(ctrl.on_package_selected)

        self._ctrl = ctrl
        self._pages = pages
