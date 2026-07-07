"""A ``QAbstractItemModel`` adapter over the frontend-agnostic ``TreeNode``.

The model wraps ``core.tree_model.TreeNode`` so the navigation tree renders BPX
objects without duplicating any traversal logic in Qt. It is read-only:
selection drives ``AppState``; structural edits rebuild the document and the
model is reset.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from core.tree_model import TreeNode


class BpxTreeModel(QAbstractItemModel):
    """Maps a ``TreeNode`` hierarchy onto Qt's item model interface."""

    def __init__(
        self,
        root: TreeNode,
        is_expanded: Callable[[QModelIndex], bool] | None = None,
    ) -> None:
        super().__init__()
        self._root = root
        self._is_expanded = is_expanded or (lambda _index: False)

    def node_at(self, index: QModelIndex) -> TreeNode | None:
        if not index.isValid():
            return self._root
        return index.internalPointer()

    def index_for_path(self, path: tuple[str, ...]) -> QModelIndex:
        """Return the model index for the node at *path*, or an invalid index.

        Descends from the root matching each successive path prefix, so callers
        (such as a view revealing a navigation target) can locate a node
        without knowing Qt's index construction.
        """
        target = tuple(path)
        parent = QModelIndex()
        current = self._root
        for depth in range(1, len(target) + 1):
            prefix = target[:depth]
            for row, child in enumerate(current.children):
                if child.path == prefix:
                    parent = self.index(row, 0, parent)
                    current = child
                    break
            else:
                return QModelIndex()
        return parent

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
            return f"{node.label} ⚠" if self._shows_error_marker(index, node) else node.label
        if role == Qt.ToolTipRole:
            return node.description or node.label
        return None

    def refresh_warning_markers(self) -> None:
        self._emit_data_changed(QModelIndex())

    def _find_parent(self, current: TreeNode, target: TreeNode) -> TreeNode | None:
        for child in current.children:
            if child is target:
                return current
            found = self._find_parent(child, target)
            if found is not None:
                return found
        return None

    def _shows_error_marker(self, index: QModelIndex, node: TreeNode) -> bool:
        if node.has_direct_errors or node.has_direct_parameter_errors:
            return True
        if not self._is_expanded(index):
            return any(child.has_errors for child in node.children)
        return False

    def _emit_data_changed(self, parent: QModelIndex) -> None:
        for row in range(self.rowCount(parent)):
            index = self.index(row, 0, parent)
            self.dataChanged.emit(index, index, [Qt.DisplayRole])
            self._emit_data_changed(index)
