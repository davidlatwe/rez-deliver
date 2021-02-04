

# TODO:
#   - view github releases
#   - view package details, e.g. dependencies, variants, descriptions
#   - deploy buttons, log

from ..vendor.Qt5 import QtWidgets
from ..common.view import JsonView


class InstallerView(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(InstallerView, self).__init__(parent=parent)

        page = {
            "detail": JsonView(),
        }

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(page["detail"])

        self._page = page

    def set_model(self, model):
        self._page["detail"].setModel(model)

    def on_tag_fetched(self, repo, tags):
        # verify fetched repo matches current selected package's repo
        print(repo, tags)
