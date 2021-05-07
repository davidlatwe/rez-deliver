
from .vendor.Qt5 import QtCore, QtGui
from . import common
from ..api import PackageInstaller

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
    ]

    def __init__(self, parent=None):
        super(PackageBookModel, self).__init__(parent=parent)
        self._groups = set()

    def name_groups(self):
        return sorted(self._groups)

    def iter_items(self):
        for item in self.root.children():
            yield item

    def iter_requests(self):
        for family in self.root.children():
            for version in family.children():
                if version["_isChecked"] == QtCheckState.Unchecked:
                    continue

                if version["numVariants"]:
                    states = [v["_isChecked"] for v in version.children()]

                    if all(s == QtCheckState.Checked for s in states):
                        yield version["name"], None

                    else:
                        for index, s in enumerate(states):
                            if s == QtCheckState.Checked:
                                yield version["name"], index

                else:
                    yield version["name"], None

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


class PackageManifestModel(common.model.AbstractTableModel):
    Headers = [
        "status",
        "name",
        "variant",
    ]

    Status = PackageInstaller.StatusMapStr

    def clear(self):
        self.beginResetModel()
        self.items.clear()
        self.endResetModel()

    def load(self, manifest):
        self.beginResetModel()
        self.items.clear()

        for requested in manifest:
            self.items.append({
                "status": requested.status,
                "name": requested.name,
                "variant": requested.index,
                # TODO: requested.depended
            })

        self.endResetModel()

    def findVariant(self, name, variant):
        return next(i for i in self.items
                    if i["name"] == name and i["variant"] == variant)

    def findVariantIndex(self, name, variant, column=0):
        row = self.items.index(self.findVariant(name, variant))
        return self.createIndex(row, column, QtCore.QModelIndex())

    def installed(self, requested):
        index = self.findVariantIndex(requested.name, requested.index)
        self.setData(index, requested.status)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        try:
            data = self.items[row]
        except IndexError:
            return None

        if col == 0 and role == QtCore.Qt.DisplayRole:
            return self.Status[data["status"]]

        if col == 1 and role == QtCore.Qt.DisplayRole:
            return data["name"]

        if col == 2 and role == QtCore.Qt.DisplayRole:
            return data["variant"]

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid():
            return None

        row = index.row()

        try:
            data = self.items[row]
        except IndexError:
            return None

        data["status"] = value
        self.dataChanged.emit(index, index)
