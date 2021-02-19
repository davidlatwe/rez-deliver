

# TODO:
#   - view package details, e.g. dependencies, variants, descriptions
#   - release target selector
#   - deploy buttons, log

from ..vendor.Qt5 import QtWidgets
from ..common.view import JsonView


class InstallerView(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(InstallerView, self).__init__(parent=parent)

        widgets = {
            "detail": JsonView(),
            "target": JsonView(),
            "install": QtWidgets.QPushButton("Install"),
        }

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(widgets["target"])
        layout.addWidget(widgets["detail"])
        layout.addWidget(widgets["install"])

        self._widgets = widgets

    def set_model(self, model):
        self._widgets["detail"].setModel(model)
