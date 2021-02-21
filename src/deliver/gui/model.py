
from .vendor.Qt5 import QtCore, QtGui
from . import common

QtCheckState = QtCore.Qt.CheckState


class PackageBookItem(common.model.TreeItem):
    def __init__(self, data=None):
        super(PackageBookItem, self).__init__(data or {})
        self["_isChecked"] = QtCheckState.Unchecked

    def is_variant(self):
        return "index" in self.keys()


class PackageBookModel(common.model.AbstractTreeModel):
    ItemRole = QtCore.Qt.UserRole + 10
    FilterRole = QtCore.Qt.UserRole + 11
    CompletionRole = QtCore.Qt.UserRole + 12
    CompletionColumn = 0
    Headers = [
        "name",
        "tools",
    ]

    def __init__(self, parent=None):
        super(PackageBookModel, self).__init__(parent=parent)
        self._groups = set()

    def name_groups(self):
        return sorted(self._groups)

    def iter_items(self):
        for item in self.root.children():
            yield item

    def reset(self, items=None):
        self.beginResetModel()
        self._groups.clear()
        family = None
        families = set()

        def cover_previous_family():
            if family:
                family["tools"] = ", ".join(sorted(family["tools"]))

        for item in sorted(items or [], key=lambda i: i["family"].lower()):
            family_name = item["family"]
            tools = item["tools"][:]
            initial = family_name[0].upper()

            item.update({
                "_type": "version",
                "_group": initial,
                "name": item["qualified_name"],
                "family": family_name,
                "tools": ", ".join(sorted(tools)),
            })
            package = PackageBookItem(item)

            for index in range(item["numVariants"]):
                variant = PackageBookItem(item)
                variant["name"] += "[%d]" % index
                variant["index"] = index
                package.add_child(variant)

            if family_name not in families:
                cover_previous_family()

                family = PackageBookItem({
                    "_type": "family",
                    "_group": initial,
                    "name": family_name,
                    "family": family_name,
                    "version": "",
                    "tools": set(),  # later be formatted from all versions
                })

                families.add(family_name)
                self._groups.add(initial)
                self.add_child(family)

            family["tools"].update(tools)
            family.add_child(package)

        cover_previous_family()

        self.endResetModel()

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None

        if role == self.CompletionRole:
            item = index.internalPointer()
            if item["_type"] == "family":
                return item["family"]
            else:
                return item["version"]

        if role == QtCore.Qt.DisplayRole:
            col = index.column()
            item = index.internalPointer()
            key = self.Headers[col]
            return item[key]

        if role == QtCore.Qt.ForegroundRole:
            col = index.column()
            item = index.internalPointer()
            if item["_type"] == "version" and col == 0:
                return QtGui.QColor("gray")

        if role == QtCore.Qt.CheckStateRole:
            if index.column() == 0 and index.parent().isValid():
                # only versions and variants are checkable
                item = index.internalPointer()
                return item["_isChecked"]

        if role == self.FilterRole:
            item = index.internalPointer()
            return ", ".join([item["family"], item["tools"]])

        if role == self.ItemRole:
            item = index.internalPointer()
            return item

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if role == QtCore.Qt.CheckStateRole:
            if index.column() == 0 and index.parent().isValid():
                # only versions and variants are checkable

                parent = index.parent()
                item = index.internalPointer()
                item["_isChecked"] = value

                if item.is_variant():
                    # Was ticking on variant, update variant and version
                    version = parent.internalPointer()
                    variants = version.children()

                    unchecked_count = sum(
                        v["_isChecked"] == QtCheckState.Unchecked
                        for v in variants
                    )

                    if unchecked_count == 0:
                        version["_isChecked"] = QtCheckState.Checked
                    elif unchecked_count == len(variants):
                        version["_isChecked"] = QtCheckState.Unchecked
                    else:
                        version["_isChecked"] = QtCheckState.PartiallyChecked

                    self.dataChanged.emit(index, index)
                    self.dataChanged.emit(parent, parent)

                else:
                    # Was ticking on version, update version and all variants
                    variants = item.children()

                    for variant in variants:
                        variant["_isChecked"] = value

                    if len(variants):
                        first = index.child(0, 0)
                        last = index.child(len(variants) - 1, 0)
                        self.dataChanged.emit(first, last)
                    self.dataChanged.emit(index, index)

        return super(PackageBookModel, self).setData(index, value, role)

    def flags(self, index):
        if index.column() == 0 and index.parent().isValid():
            # only versions and variants are checkable
            return (
                QtCore.Qt.ItemIsEnabled |
                QtCore.Qt.ItemIsSelectable |
                QtCore.Qt.ItemIsUserCheckable
            )

        return super(PackageBookModel, self).flags(index)


class PackageBookProxyModel(QtCore.QSortFilterProxyModel):

    def __init__(self, parent=None):
        super(PackageBookProxyModel, self).__init__(parent=parent)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setFilterRole(PackageBookModel.FilterRole)


class StringFormatModel(common.model.AbstractTableModel):
    formatted = QtCore.Signal()
    ItemRole = QtCore.Qt.UserRole + 10
    ValuesRole = QtCore.Qt.UserRole + 11
    Headers = [
        "key",
        "value",
    ]

    def __init__(self, parent=None):
        super(StringFormatModel, self).__init__(parent=parent)
        self.items = []

    def load(self, data):
        self.beginResetModel()
        self.items.clear()

        for key, values in data.items():
            default = values[0]
            item = {
                "key": key,
                "value": default[1],  # TODO: load previous selection
                "_val_": default[0],
                "values": values,
            }
            self.items.append(item)

        self.endResetModel()

    def kwargs(self):
        return {item["key"]: item["_val_"] for item in self.items}

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None

        if role == QtCore.Qt.DisplayRole:
            col = index.column()
            row = index.row()
            item = self.items[row]
            key = self.Headers[col]
            return item[key]

        if role == self.ValuesRole:
            row = index.row()
            item = self.items[row]
            return item["values"][:]

        if role == self.ItemRole:
            row = index.row()
            item = self.items[row]
            return item.copy()

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if index.column() == 1:
            row = index.row()
            item = self.items[row]
            item["_val_"] = value[0]
            item["value"] = value[1]

            self.dataChanged.emit(index, index)
            self.formatted.emit()

    def flags(self, index):
        if index.column() == 1:
            return (
                QtCore.Qt.ItemIsEnabled |
                QtCore.Qt.ItemIsEditable |
                ~QtCore.Qt.ItemIsSelectable
            )

        return QtCore.Qt.NoItemFlags
