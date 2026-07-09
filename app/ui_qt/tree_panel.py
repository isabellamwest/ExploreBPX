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
        self._view.setObjectName("StructureTree")
        self._view.setHeaderHidden(True)
        self._view.clicked.connect(self._on_clicked)
        self._view.expanded.connect(self._refresh_warning_markers)
        self._view.collapsed.connect(self._refresh_warning_markers)
        layout.addWidget(self._view)

    def set_root(self, root: TreeNode) -> None:
        model = BpxTreeModel(root, is_expanded=self._view.isExpanded)
        self._view.setModel(model)
        self._view.expandToDepth(1)
        model.refresh_warning_markers()

    def reveal(self, path: tuple[str, ...]) -> None:
        """Expand ancestors of, select, and scroll to the node at *path*.

        This is the tree's part of a navigation reveal; it owns no navigation
        logic and reacts only to a resolved target path.
        """
        model = self._view.model()
        if not isinstance(model, BpxTreeModel):
            return
        index = model.index_for_path(tuple(path))
        if not index.isValid():
            return
        parent = index.parent()
        while parent.isValid():
            self._view.expand(parent)
            parent = parent.parent()
        self._view.setCurrentIndex(index)
        self._view.scrollTo(index)

    def focus_tree(self) -> None:
        """Give keyboard focus to the tree view (e.g. when search is dismissed)."""
        self._view.setFocus()

    def _on_clicked(self, index: QModelIndex) -> None:
        node = index.internalPointer()
        if node is not None:
            self.node_selected.emit(node.path)

    def _refresh_warning_markers(self, _index: QModelIndex) -> None:
        model = self._view.model()
        if isinstance(model, BpxTreeModel):
            model.refresh_warning_markers()
