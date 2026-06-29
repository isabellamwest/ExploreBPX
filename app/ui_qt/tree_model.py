"""A ``QAbstractItemModel`` adapter over the frontend-agnostic ``TreeNode``.

The model wraps ``core.tree_model.TreeNode`` so the navigation tree renders BPX
objects without duplicating any traversal logic in Qt. It is read-only:
selection drives ``AppState``; structural edits rebuild the document and the
model is reset.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from core.tree_model import TreeNode


class BpxTreeModel(QAbstractItemModel):
    """Maps a ``TreeNode`` hierarchy onto Qt's item model interface."""

    def __init__(self, root: TreeNode) -> None:
        super().__init__()
        self._root = root

    def node_at(self, index: QModelIndex) -> TreeNode | None:
        if not index.isValid():
            return self._root
        return index.internalPointer()

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        parent_node = self.node_at(parent)
        if parent_node is None or row >= len(parent_node.children):
            return QModelIndex()
        return self.createIndex(row, column, parent_node.children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        child = index.internalPointer()
        parent = self._find_parent(self._root, child)
        if parent is None or parent is self._root:
            return QModelIndex()
        grandparent = self._find_parent(self._root, parent)
        siblings = grandparent.children if grandparent else [self._root]
        return self.createIndex(siblings.index(parent), 0, parent)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        node = self.node_at(parent)
        return len(node.children) if node else 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        node: TreeNode = index.internalPointer()
        if role == Qt.DisplayRole:
            return f"{node.label} ⚠" if node.has_errors else node.label
        if role == Qt.ToolTipRole:
            return node.description or node.label
        return None

    def _find_parent(self, current: TreeNode, target: TreeNode) -> TreeNode | None:
        for child in current.children:
            if child is target:
                return current
            found = self._find_parent(child, target)
            if found is not None:
                return found
        return None
