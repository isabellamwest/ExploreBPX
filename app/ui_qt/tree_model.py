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

from .parameter_row import REF_BAR_ROLE, SEVERITY_ROLE

#: Item-data role carrying a section's differ count (DIFFERS+FILLABLE rows,
#: multi-file track M2), painted right-aligned by ``_TreeItemDelegate``
#: alongside the reference gutter bar (:data:`~ui_qt.parameter_row.
#: REF_BAR_ROLE`, re-exported here for the tree's own use). ``None``/absent
#: with no comparison docked or a zero count -- the old text-appended
#: "≠ N" label suffix moved here so the mark paints like the parameter
#: list's, not as row text.
REF_COUNT_ROLE = Qt.UserRole + 106


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
        visible_error_paths: frozenset[tuple[str, ...]] = frozenset(),
    ) -> None:
        super().__init__()
        self._root = root
        self._is_expanded = is_expanded or (lambda _index: False)
        #: Reference comparison (multi-file track M2), or ``None`` with no
        #: reference docked (or its decoration hidden). See ``set_comparison``.
        self._comparison = comparison
        #: Section paths whose dot should show: page-visible errors only
        #: (``core.completion.visible_error_section_paths``, decisions P/G).
        #: The marker deliberately does NOT read ``node.has_direct_errors``/
        #: ``parameter.has_errors`` -- those are validator-verbatim and
        #: include absorbed (outstanding) diagnostics, so a merely-unfilled
        #: section would read as broken while the parameter list and rail
        #: badge call the same state calm.
        self._visible_error_paths = frozenset(visible_error_paths)

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
            return label
        if role == SEVERITY_ROLE:
            return "error" if self._shows_error_marker(index, node) else None
        if role == REF_BAR_ROLE:
            return self._ref_bar(index, node)
        if role == REF_COUNT_ROLE:
            count = self._ref_count(index, node)
            return count or None
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
        if node.path in self._visible_error_paths:
            return True
        if not self._is_expanded(index):
            # Collapsed rollup: a hidden descendant's dot surfaces on the
            # deepest visible ancestor (prefix match over section paths).
            depth = len(node.path)
            return any(path[:depth] == node.path for path in self._visible_error_paths)
        return False

    def _ref_bar(self, index: QModelIndex, node: TreeNode) -> str | None:
        """This node's reference gutter-bar variant (multi-file track M2
        reference comparison): an expanded row reads its own section only;
        a collapsed row rolls up self plus every descendant section (same
        prefix-match idiom as :meth:`_shows_error_marker`), so a purple rail
        on a collapsed parent means "something differs underneath", not just
        here. ``None`` with no comparison docked."""
        if self._comparison is None:
            return None
        if not self._is_expanded(index):
            depth = len(node.path)
            variants = [
                self._section_bar(path)
                for path in self._comparison.sections
                if path[:depth] == node.path
            ]
            if "differs" in variants:
                return "differs"
            if "equal" in variants:
                return "equal"
            return None
        return self._section_bar(node.path)

    def _ref_count(self, index: QModelIndex, node: TreeNode) -> int:
        """This node's differ count: this section's own DIFFERS+FILLABLE
        rows when expanded, summed over self plus every descendant section
        when collapsed -- the numeric companion to :meth:`_ref_bar`, 0 with
        no comparison docked."""
        if self._comparison is None:
            return 0
        if not self._is_expanded(index):
            depth = len(node.path)
            return sum(
                self._section_differ_count(path)
                for path in self._comparison.sections
                if path[:depth] == node.path
            )
        return self._section_differ_count(node.path)

    def _section_bar(self, path: tuple[str, ...]) -> str | None:
        """One section's own bar variant: "differs" if it has any
        differing/fillable row, "equal" if it has no differences but at
        least one row that matches the reference exactly, else ``None`` --
        a main-only section (absent from the reference entirely) or a pure
        container with no rows of its own (e.g. Parameterisation) never
        shows a bar."""
        section = self._comparison.section(path) if self._comparison else None
        if section is None or section.is_main_only:
            return None
        if section.differ_count > 0:
            return "differs"
        return "equal" if section.has_equal_row else None

    def _section_differ_count(self, path: tuple[str, ...]) -> int:
        section = self._comparison.section(path) if self._comparison else None
        if section is None or section.is_main_only:
            return 0
        return section.differ_count

    def _emit_data_changed(self, parent: QModelIndex) -> None:
        for row in range(self.rowCount(parent)):
            index = self.index(row, 0, parent)
            self.dataChanged.emit(index, index, [Qt.DisplayRole])
            self._emit_data_changed(index)
