"""Parameter list (middle panel): direct parameters of the selected object."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from core.tree_model import TreeNode


class ParameterListPanel(QWidget):
    """Lists a node's parameters; emits the selected parameter's path."""

    parameter_selected = Signal(tuple)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_clicked)
        layout.addWidget(self._list)

    def show_node(self, node: TreeNode | None) -> None:
        self._list.clear()
        if node is None:
            return
        for parameter in node.parameters:
            marker = "  ⚠" if parameter.has_errors else ""
            item = QListWidgetItem(f"{parameter.label}{marker}")
            item.setData(256, parameter.path)
            self._list.addItem(item)

    def reveal(self, node: TreeNode | None, parameter_path: tuple[str, ...] | None) -> None:
        """Show *node*'s parameters and select/scroll to *parameter_path*.

        This is the parameter list's part of a navigation reveal; it re-lists
        the target object's parameters and highlights the target row when the
        navigation is parameter-level.
        """
        self.show_node(node)
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
