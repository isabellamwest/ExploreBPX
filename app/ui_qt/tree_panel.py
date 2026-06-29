"""Navigation tree (left panel): BPX objects only, backed by ``BpxTreeModel``."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, Signal
from PySide6.QtWidgets import QTreeView, QVBoxLayout, QWidget

from core.tree_model import TreeNode

from .tree_model import BpxTreeModel


class TreePanel(QWidget):
    """Object tree; emits the selected node's path."""

    node_selected = Signal(tuple)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._view = QTreeView()
        self._view.setHeaderHidden(True)
        self._view.clicked.connect(self._on_clicked)
        layout.addWidget(self._view)

    def set_root(self, root: TreeNode) -> None:
        model = BpxTreeModel(root)
        self._view.setModel(model)
        self._view.expandToDepth(1)

    def _on_clicked(self, index: QModelIndex) -> None:
        node = index.internalPointer()
        if node is not None:
            self.node_selected.emit(node.path)
