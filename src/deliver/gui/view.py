
from Qt5 import QtWidgets
from .search.view import PackageView


class Window(QtWidgets.QWidget):

    def __init__(self, ctrl, parent=None):
        super(Window, self).__init__(parent=parent)

        pages = {
            "package": PackageView(),
        }

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(pages["package"])

        pages["package"].set_model(ctrl.models["package"])

        self._ctrl = ctrl
        self._pages = pages
