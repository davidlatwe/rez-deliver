
from Qt5 import QtWidgets
from .search.view import PackageView
from .installer.view import InstallerView


class Window(QtWidgets.QWidget):

    def __init__(self, ctrl, parent=None):
        super(Window, self).__init__(parent=parent)

        pages = {
            "package": PackageView(),
            "installer": InstallerView(),
        }

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(pages["package"])
        layout.addWidget(pages["installer"])

        # setup
        pages["package"].set_model(ctrl.models["package"])
        pages["installer"].set_model(ctrl.models["detail"])

        # signals
        pages["package"].selected.connect(ctrl.on_package_selected)

        self._ctrl = ctrl
        self._pages = pages
