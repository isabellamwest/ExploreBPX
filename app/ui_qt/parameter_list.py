"""Parameter list (middle panel): direct parameters of the selected object.

The pane also hosts the section-scoped "+ Add parameter" entry point: a
header button, enabled only when a document is loaded and an object is
selected, that opens :class:`~.add_parameter_popup.AddParameterPopup`
anchored underneath it. This is deliberately the only add-parameter surface
-- the app has no context menus.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.tree_model import TreeNode

from .add_parameter_popup import AddParameterPopup


class ParameterListPanel(QWidget):
    """Lists a node's parameters; emits the selected parameter's path."""

    parameter_selected = Signal(tuple)
    add_parameter_requested = Signal(tuple, str)  # (section_path, typed_alias)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._node: TreeNode | None = None
        self._model: str | None = None

        self._add_button = QPushButton("+ Add parameter")
        self._add_button.setObjectName("AddParameterButton")
        self._add_button.setEnabled(False)
        self._add_button.setMinimumHeight(28)
        self._add_button.clicked.connect(self._open_add_popup)

        button_container = QWidget()
        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(8, 8, 8, 8)
        button_layout.addWidget(self._add_button)
        layout.addWidget(button_container)

        self._list = QListWidget()
        self._list.setObjectName("ParameterListView")
        self._list.itemClicked.connect(self._on_clicked)
        layout.addWidget(self._list)

        self._popup = AddParameterPopup(self)
        self._popup.custom_parameter_requested.connect(self._on_custom_parameter_requested)

    def show_node(self, node: TreeNode | None, model: str | None = None) -> None:
        self._node = node
        self._model = model
        self._add_button.setEnabled(node is not None)
        self._list.clear()
        if node is None:
            return
        for parameter in node.parameters:
            marker = "  ⚠" if parameter.has_errors else ""
            item = QListWidgetItem(f"{parameter.label}{marker}")
            item.setData(256, parameter.path)
            self._list.addItem(item)

    def reveal(
        self,
        node: TreeNode | None,
        parameter_path: tuple[str, ...] | None,
        model: str | None = None,
    ) -> None:
        """Show *node*'s parameters and select/scroll to *parameter_path*.

        This is the parameter list's part of a navigation reveal; it re-lists
        the target object's parameters and highlights the target row when the
        navigation is parameter-level. *model* is the document's declared
        model, needed (alongside the section path) to look up BPX-alias
        suggestions for the add-parameter popup.
        """
        self.show_node(node, model)
        if parameter_path is None:
            return
        target = tuple(parameter_path)
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(256) == target:
                self._list.setCurrentRow(row)
                self._list.scrollToItem(item)
                return

    def _on_clicked(self, item: QListWidgetItem) -> None:
        self.parameter_selected.emit(item.data(256))

    def _open_add_popup(self) -> None:
        if self._node is None:
            return
        existing = {parameter.label for parameter in self._node.parameters}
        self._popup.open_for_section(
            self._add_button,
            self._node.label,
            existing,
            self._node.path,
            self._model,
        )

    def _on_custom_parameter_requested(self, typed_alias: str) -> None:
        if self._node is None:
            return
        self.add_parameter_requested.emit(self._node.path, typed_alias)
