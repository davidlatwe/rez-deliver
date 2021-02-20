
from .vendor.Qt5 import QtCore, QtWidgets
from . import model


class StringFormatValueDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that display version integer formatted as version string."""

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QComboBox(parent)

        def commit_data():
            self.commitData.emit(editor)  # Update model data
        editor.currentIndexChanged.connect(commit_data)

        return editor

    def setEditorData(self, editor, index):
        editor.clear()

        # Current value of the index
        current = index.data(QtCore.Qt.DisplayRole)
        values = index.data(model.StringFormatModel.ValuesRole)

        index = 0
        for i, value in enumerate(values):
            label = value[1]
            editor.addItem(label, userData=value)

            if label == current:
                index = i

        editor.setCurrentIndex(index)  # Will trigger index-change signal

    def setModelData(self, editor, model_, index):
        """Apply the integer version back in the model"""
        value = editor.itemData(editor.currentIndex())
        model_.setData(index, value)
