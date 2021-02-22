
from .vendor.Qt5 import QtCore, QtWidgets
from . import common, model, delegate

# TODO:
#   * parse request into model item check state
#   * add reset button
#   * log model reset time
#   * no-local-package checkBox
#   * show package paths, and able to update package list per path


class PackageBookTreeView(common.view.VerticalExtendedTreeView):
    def __init__(self, parent=None):
        super(PackageBookTreeView, self).__init__(parent=parent)
        self.setObjectName("PackageBookTreeView")
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.sortByColumn(0, QtCore.Qt.AscendingOrder)


class PackageBookTabBar(common.view.VerticalDocTabBar):
    def __init__(self, parent=None):
        super(PackageBookTabBar, self).__init__(parent=parent)
        self.setObjectName("PackageBookTabBar")
        self.setMinimumHeight(120)


class PackageBookView(QtWidgets.QWidget):
    """Single page tab widget"""
    selected = QtCore.Signal(str, int)  # package name, variant index

    def __init__(self, parent=None):
        super(PackageBookView, self).__init__(parent=parent)
        self.setObjectName("PackageBookView")

        widgets = {
            "search": QtWidgets.QLineEdit(),
            "book": QtWidgets.QWidget(),
            "page": QtWidgets.QWidget(),
            "side": QtWidgets.QWidget(),
            "view": PackageBookTreeView(),
            "tab": PackageBookTabBar(),
        }
        widgets["page"].setObjectName("PackageBookPage")
        widgets["side"].setObjectName("PackageBookSide")

        widgets["search"].setPlaceholderText(" Search by family or tool..")

        # Layouts..
        layout = QtWidgets.QVBoxLayout(widgets["side"])
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widgets["tab"])
        layout.addStretch(100)
        layout.setSpacing(0)

        layout = QtWidgets.QVBoxLayout(widgets["page"])
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(widgets["view"])

        layout = QtWidgets.QHBoxLayout(widgets["book"])
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widgets["side"])
        layout.addWidget(widgets["page"])
        layout.setSpacing(0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(widgets["search"])
        layout.addSpacing(6)
        layout.addWidget(widgets["book"])
        layout.setSpacing(0)

        # Signals..
        header = widgets["view"].header()
        scroll = widgets["view"].verticalScrollBar()

        widgets["tab"].currentChanged.connect(self.on_tab_clicked)
        widgets["search"].textChanged.connect(self.on_searched)
        header.sortIndicatorChanged.connect(self.on_sort_changed)
        scroll.valueChanged.connect(self.on_scrolled)

        self._widgets = widgets
        self._groups = []

    def init_column_width(self):
        # ignore this if window geo saved
        self._widgets["view"].setColumnWidth(0, 380)  # name

    def set_model(self, model_):
        proxy = model.PackageBookProxyModel()
        proxy.setSourceModel(model_)
        self._widgets["view"].setModel(proxy)

        sel_model = self._widgets["view"].selectionModel()
        sel_model.selectionChanged.connect(self.on_selection_changed)

        model_.modelReset.connect(self.on_model_reset)

    def model(self):
        proxy = self._widgets["view"].model()
        return proxy.sourceModel()

    def proxy(self):
        return self._widgets["view"].model()

    def on_searched(self, text):
        view = self._widgets["view"]
        proxy = self.proxy()
        proxy.setFilterRegExp(text)
        view.reset_extension()

    def on_tab_clicked(self, index):
        tab = self._widgets["tab"]
        view = self._widgets["view"]
        proxy = self.proxy()
        model_ = self.model()

        group = tab.tabText(index)
        for i, item in enumerate(model_.iter_items()):
            if item["_group"] == group:
                index = model_.index(i, 0)
                index = proxy.mapFromSource(index)
                view.scroll_at_top(index)
                return

    def on_scrolled(self, value):
        if not self._widgets["tab"].isEnabled():
            return

        tab = self._widgets["tab"]
        view = self._widgets["view"]
        proxy = self.proxy()
        model_ = self.model()

        index = view.top_scrolled_index(value)
        index = proxy.mapToSource(index)
        name = model_.data(index)
        if name:
            group = name[0].upper()
            index = self._groups.index(group)
            tab.blockSignals(True)
            tab.setCurrentIndex(index)
            tab.blockSignals(False)

    def on_sort_changed(self, index, order):
        is_sort_name = index == 0
        tab = self._widgets["tab"]

        tab.setEnabled(is_sort_name)
        if is_sort_name:
            if len(self._groups) <= 1:
                return

            first, second = self._groups[:2]
            is_ascending = int(first > second)
            if is_ascending == int(order):
                return

            self._groups.reverse()
            for i, group in enumerate(self._groups):
                tab.setTabText(i, group)

    def on_model_reset(self):
        tab = self._widgets["tab"]
        model_ = self.model()

        self._groups.clear()
        for index in range(tab.count()):
            tab.removeTab(index)

        for group in model_.name_groups():
            self._groups.append(group)
            tab.addTab(group)

        # (MacOS) Ensure tab bar *polished* even it's not visible on launch.
        tab.updateGeometry()

    def on_selection_changed(self, selected, deselected):
        selected = selected.indexes()
        if selected:
            item = selected[0].data(role=model.PackageBookModel.ItemRole)
            self.selected.emit(item.get("qualified_name", item["family"]),
                               item.get("index", -1))
        else:
            self.selected.emit("", -1)


class PackageDependencyView(QtWidgets.QWidget):
    pass


class PackageDataView(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(PackageDataView, self).__init__(parent=parent)

        # panels = {
        #     "data": QtWidgets.QWidget(),  # name, version, desc...
        #     "variants": None,
        #     "dependencies": None,  # (build context resolved pkgs)
        # }

        widgets = {
            "name": QtWidgets.QLineEdit(),
            "version": QtWidgets.QLineEdit(),
            "description": QtWidgets.QTextEdit(),
        }

        widgets["name"].setReadOnly(True)
        widgets["version"].setReadOnly(True)
        widgets["description"].setReadOnly(True)
        widgets["description"].setMaximumHeight(120)

        layout = QtWidgets.QFormLayout(self)
        layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignCenter)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addRow("Name:", widgets["name"])
        layout.addRow("Version:", widgets["version"])
        layout.addRow("Description:", widgets["description"])
        layout.addRow("", QtWidgets.QLabel())  # stretch

        self._widgets = widgets

    def parse_package(self, package, is_variant):
        data = package.data
        self._widgets["name"].setText(data["name"])
        self._widgets["version"].setText(data.get("version", ""))
        self._widgets["description"].setText(data.get("description", ""))


class StringFormatView(common.view.SlimTableView):

    def __init__(self, parent=None):
        super(StringFormatView, self).__init__(parent=parent)


class InstallerView(QtWidgets.QWidget):

    targeted = QtCore.Signal(str)
    installed = QtCore.Signal()

    # TODO:
    #   - view package details, e.g. dependencies, variants, descriptions
    #   - release target selector
    #   - deploy buttons, log

    # Release
    # - Target:
    # - Keys:
    # - Path:
    # - Manifest:

    def __init__(self, parent=None):
        super(InstallerView, self).__init__(parent=parent)

        widgets = {
            "targets": QtWidgets.QComboBox(),
            "keys": StringFormatView(),
            "path": QtWidgets.QLineEdit(),
            "install": QtWidgets.QPushButton("Install"),
        }

        widgets["keys"].setItemDelegateForColumn(
            1, delegate.StringFormatValueDelegate()
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(widgets["targets"])
        layout.addWidget(widgets["path"])
        layout.addWidget(widgets["keys"])
        layout.addWidget(widgets["install"])

        widgets["targets"].currentTextChanged.connect(self.targeted.emit)
        widgets["install"].clicked.connect(self.installed.emit)

        self._widgets = widgets

    def set_model(self, model_t, model_k):
        self._widgets["targets"].setModel(model_t)
        self._widgets["keys"].setModel(model_k)

    def set_path(self, path):
        self._widgets["path"].setText(path)
