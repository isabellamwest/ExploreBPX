"""A ``QAbstractItemModel`` adapter over the frontend-agnostic ``TreeNode``.

The model wraps ``core.tree_model.TreeNode`` so the navigation tree renders BPX
objects without duplicating any traversal logic in Qt. It is read-only:
selection drives ``AppState``; structural edits rebuild the document and the
model is reset.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from core import structure
from core.compare import ComparisonResult
from core.tree_model import TreeNode

from .parameter_row import SEVERITY_ROLE


def _is_user_defined_content(node: TreeNode) -> bool:
    """True for a user-authored subsection inside the open ``User-defined``
    bucket -- not the bucket itself, whose name is a fixed schema property.

    Composed from the two structural predicates: ``is_freeform_section`` holds
    for the bucket and its subsections, ``can_rename`` narrows that to the
    user-owned ones (excluding the bucket). These are the tree's only
    free-form, user-named sections, tagged so they read apart from the fixed
    schema sections (materials/runs are not free-form and stay untagged)."""
    return structure.is_freeform_section(node.path) and structure.can_rename(node.path)


class BpxTreeModel(QAbstractItemModel):
    """Maps a ``TreeNode`` hierarchy onto Qt's item model interface."""

    def __init__(
        self,
        root: TreeNode,
        is_expanded: Callable[[QModelIndex], bool] | None = None,
        comparison: ComparisonResult | None = None,
    ) -> None:
        super().__init__()
        self._root = root
        self._is_expanded = is_expanded or (lambda _index: False)
        #: Reference comparison (multi-file track M2), or ``None`` with no
        #: reference docked (or its decoration hidden). See ``set_comparison``.
        self._comparison = comparison

    def set_comparison(self, comparison: ComparisonResult | None) -> None:
        """Update the comparison result and repaint every node's label."""
        self._comparison = comparison
        self._emit_data_changed(QModelIndex())

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
            label = node.label
            if _is_user_defined_content(node):
                label = f"{label} · custom"
            differ_count = self._differ_count(node)
            if differ_count:
                label = f"{label} ≠ {differ_count}"
            return label
        if role == SEVERITY_ROLE:
            return "error" if self._shows_error_marker(index, node) else None
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

    def _differ_count(self, node: TreeNode) -> int:
        """This section's own DIFFERS+FILLABLE row count (multi-file track
        M2), or 0 with no comparison docked/visible. Text-appended to the
        label the same way the "· custom" tag is (decision 12) -- no ghost
        counts here, and no new widget/delegate."""
        if self._comparison is None:
            return 0
        section = self._comparison.section(node.path)
        return section.differ_count if section is not None else 0

    def _emit_data_changed(self, parent: QModelIndex) -> None:
        for row in range(self.rowCount(parent)):
            index = self.index(row, 0, parent)
            self.dataChanged.emit(index, index, [Qt.DisplayRole])
            self._emit_data_changed(index)
