"""Navigation tree (left panel): BPX objects only, backed by ``BpxTreeModel``.

The tree is also where the document's *structure* is edited, via the same
right-click convention as the parameter list: a context menu on the node it
lands on, offering only what is legal **there** (nothing disabled, nothing
invented):

- ``Add section ▸`` -- the schema-expected child sections absent from the
  node (``structure.addable_child_sections``, which resolves the electrode
  single/blended union from the electrode's own live content -- a
  ``"Particle"`` key means blended, anything else means single). Right-clicking
  empty space addresses the invisible document root, which is how the
  optional top-level sections (State, Validation) are added.
- ``Add material… / Add experiment…`` -- on the two dict-keyed containers
  whose children the user names (``structure.named_child_noun``), via an
  anchored one-field popup.
- ``Add subsection…`` -- on the open ``User-defined`` bucket and any
  subsection within it (``structure.is_freeform_section``), for nesting
  further named sections. Free-form *parameters* are added the usual way, via
  the parameter list's "+ Add parameter" -- not duplicated here.
- ``Rename…`` -- only on user-named keys (materials, Validation runs, and
  User-defined content; ``structure.can_rename``). Schema property names are
  never editable.
- ``Remove / Remove section`` -- anything ``structure.can_remove`` allows,
  required or not ("guidance informs; it does not lock"); the *window*
  confirms when the target is populated.

The panel owns no document logic: menu entries emit requests with paths and
names, and the window turns them into commands.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core import structure
from core.compare import ComparisonResult
from core.tree_model import TreeNode

from . import style
from .name_popup import NamePopup
from .parameter_row import MARK_BOX, REF_BAR_ROLE, SEVERITY_ROLE, paint_ref_bar, paint_severity_dot
from .tree_model import BpxTreeModel


class _TreeItemDelegate(QStyledItemDelegate):
    """Paints a tree row's default content, plus two optional marks layered
    on top:

    - A reference gutter bar (:data:`~ui_qt.parameter_row.REF_BAR_ROLE`),
      flush against the viewport's left edge at every depth -- one
      continuous rail rather than a per-depth indent, using the same painter
      (:func:`ui_qt.parameter_row.paint_ref_bar`) and colours as the
      parameter list's own bar. Bar only, no number beside it: with several
      references pinned, a single differ count cannot say which reference it
      counts (multi-reference design rule 6).
    - For a node flagged via :data:`ui_qt.parameter_row.SEVERITY_ROLE`
      (errors only, *page-visible* per
      ``core.completion.visible_error_section_paths`` -- absorbed/
      outstanding diagnostics never light it), a small red dot after its
      label text (:func:`ui_qt.parameter_row.paint_severity_dot`), the same
      painted mark the parameter list's issue rows use.
    """

    #: Gap between the end of the label text and the dot's box.
    _GAP = 6

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)

        self._paint_ref_bar(painter, option, index)

        if index.data(SEVERITY_ROLE) != "error":
            return
        # Position off the style's own text sub-rect, not option.rect: the
        # stylesheet's ::item padding shifts where the label actually starts,
        # and ignoring it left the dot touching the last glyph. Vertically
        # the dot centres on the label's cap midline (baseline minus half the
        # cap height) -- the row rect's geometric centre sits below the text's
        # optical centre, which read as the dot riding high.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        widget_style = widget.style() if widget is not None else QApplication.style()
        text_rect = widget_style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
        metrics = QFontMetrics(opt.font)
        baseline = text_rect.y() + (text_rect.height() + metrics.ascent() - metrics.descent()) // 2
        box = QRect(
            text_rect.x() + metrics.horizontalAdvance(opt.text) + self._GAP,
            round(baseline - metrics.capHeight() / 2 - MARK_BOX / 2),
            MARK_BOX,
            MARK_BOX,
        )
        paint_severity_dot(painter, box, style.ERROR)

    def _paint_ref_bar(self, painter, option: QStyleOptionViewItem, index) -> None:
        """Paint the reference gutter bar flush against the viewport's left
        edge (x=0), not the indented ``option.rect.left()`` -- every depth's
        bar lines up in one rail, the way a source-control gutter does.
        Painted after the row content so it survives the QSS selection fill,
        the same reasoning as the parameter list's own bar."""
        variant = index.data(REF_BAR_ROLE)
        if not variant:
            return
        rect = QRect(0, option.rect.top(), option.rect.width(), option.rect.height())
        paint_ref_bar(painter, rect, variant)


class TreePanel(QWidget):
    """Object tree; emits the selected node's path and structural requests."""

    node_selected = Signal(tuple)
    #: (parent_path, key): add object section ``key`` under ``parent_path``.
    #: Carries schema-named sections and user-named materials/experiments
    #: alike -- both become an ``AddSection`` command.
    add_section_requested = Signal(tuple, str)
    #: (path, new_name): rename the user-named key at ``path``.
    rename_requested = Signal(tuple, str)
    #: (path,): remove the object section at ``path``.
    remove_requested = Signal(tuple)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._view = QTreeView()
        self._view.setObjectName("StructureTree")
        self._view.setHeaderHidden(True)
        self._view.setItemDelegate(_TreeItemDelegate(self._view))
        self._view.clicked.connect(self._on_clicked)
        self._view.expanded.connect(self._refresh_warning_markers)
        self._view.collapsed.connect(self._refresh_warning_markers)
        self._view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._on_context_menu_requested)
        layout.addWidget(self._view)

        self._root: TreeNode | None = None
        #: Reference comparisons (multi-reference track), remembered across a
        #: ``set_root`` rebuild so a freshly-opened document immediately
        #: shows the still-docked references' gutter bars/differ counts. See
        #: ``set_comparison``.
        self._comparisons: list[ComparisonResult] = []
        self._popup = NamePopup(self)
        self._popup.name_chosen.connect(self._on_name_chosen)
        #: What the open popup will do with its name: ("add", container_path)
        #: or ("rename", node_path). One popup, one pending intent -- set when
        #: a menu action opens it, consumed by ``_on_name_chosen``.
        self._popup_intent: tuple[str, tuple[str, ...]] | None = None

    def set_root(
        self, root: TreeNode, visible_error_paths: frozenset[tuple[str, ...]] = frozenset()
    ) -> None:
        """*visible_error_paths* is the post-absorption dot feed
        (``core.completion.visible_error_section_paths``) -- always computed
        alongside the tree it describes, so it is passed per call rather than
        remembered across rebuilds the way ``_comparison`` is."""
        self._root = root
        model = BpxTreeModel(
            root,
            is_expanded=self._view.isExpanded,
            comparisons=self._comparisons,
            visible_error_paths=visible_error_paths,
        )
        self._view.setModel(model)
        self._view.expandToDepth(1)
        model.refresh_warning_markers()

    def set_comparison(self, comparisons: list[ComparisonResult]) -> None:
        """Set the reference comparisons (multi-reference track) and repaint
        every section's gutter bar/differ count -- called by ``MainWindow``
        on every document change and every reference dock/undock/hide
        toggle."""
        self._comparisons = comparisons
        model = self._view.model()
        if isinstance(model, BpxTreeModel):
            model.set_comparison(comparisons)

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

    # ------------------------------------------------------------------
    # Context menu (structure editing)
    # ------------------------------------------------------------------

    def _on_context_menu_requested(self, pos: QPoint) -> None:
        """Open the structure menu for the node under *pos*.

        A right-click acts on the row it lands on (made current first, so the
        target is visible), never a stale selection. Empty space resolves to
        the invisible document root -- deliberately: the root's ``Add
        section ▸`` is the only way to add State/Validation. A node with no
        legal action opens no menu (no disabled placeholders).
        """
        model = self._view.model()
        if not isinstance(model, BpxTreeModel):
            return
        index = self._view.indexAt(pos)
        node = model.node_at(index)
        if node is None:
            return
        if index.isValid():
            self._view.setCurrentIndex(index)
        menu = self._build_menu(node)
        if menu.isEmpty():
            return
        menu.exec(self._view.viewport().mapToGlobal(pos))

    def _build_menu(self, node: TreeNode) -> QMenu:
        """The legal structural actions for *node*, in a fresh menu.

        Every entry is derived from a ``core.structure`` query against the
        node's live path/value -- the menu offers nothing the backend would
        refuse and nothing the schema does not declare.
        """
        menu = QMenu(self)
        declared_model = (
            structure.infer_model(self._root.value) if self._root is not None else None
        )

        additions = structure.addable_child_sections(node.path, node.value, declared_model)
        if additions:
            # Built explicitly (not via ``addMenu(str)``): the C++ submenu must
            # be owned by its parent menu, not by a Python wrapper that goes
            # out of scope when this method returns.
            submenu = QMenu("Add section", menu)
            menu.addMenu(submenu)
            for key in additions:
                action = submenu.addAction(key)
                action.triggered.connect(
                    lambda _checked=False, path=node.path, name=key: self.add_section_requested.emit(
                        path, name
                    )
                )

        noun = structure.named_child_noun(node.path)
        if noun is not None:
            action = menu.addAction(f"Add {noun}…")
            action.triggered.connect(
                lambda _checked=False, target=node, what=noun: self._open_add_named(
                    target, what
                )
            )

        if structure.is_freeform_section(node.path):
            # The open bucket where the user freely names nested sections.
            # (Free-form parameters are added via the parameter list's
            # "+ Add parameter", like anywhere else -- no duplicate here.)
            add_sub = menu.addAction("Add subsection…")
            add_sub.triggered.connect(
                lambda _checked=False, target=node: self._open_add_named(
                    target, "subsection"
                )
            )

        if structure.can_rename(node.path):
            action = menu.addAction("Rename…")
            action.triggered.connect(
                lambda _checked=False, target=node: self._open_rename(target)
            )

        if node.path and structure.can_remove(node.path):
            # Plan vocabulary: user-named children are just "removed"; schema
            # sections read "Remove section".
            label = "Remove" if structure.can_rename(node.path) else "Remove section"
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, path=node.path: self.remove_requested.emit(path)
            )
        return menu

    # -- name popup ------------------------------------------------------
    def _open_add_named(self, node: TreeNode, noun: str) -> None:
        taken = frozenset(node.value) if isinstance(node.value, dict) else frozenset()
        self._popup_intent = ("add", node.path)
        self._popup.open_at(self._anchor_for(node), f"New {noun} name…", taken)

    def _open_rename(self, node: TreeNode) -> None:
        """Rename *node*: pre-filled with the current name, siblings taken.

        The taken set is the parent's full key set; the popup treats the
        pre-filled current name as "unchanged, no-op" rather than a collision.
        A Particle material additionally gets a note: its old name is never
        rewritten in any per-material reference elsewhere in the document
        (``core.structure.is_particle_material`` -- UI copy only, no
        validation logic here). Validation runs and User-defined content are
        never referenced by name elsewhere, so they get no note.
        """
        parent_value = _value_at(
            self._root.value if self._root is not None else None, node.path[:-1]
        )
        taken = frozenset(parent_value) if isinstance(parent_value, dict) else frozenset()
        note = (
            "State-section references are not updated; validation will flag mismatches."
            if structure.is_particle_material(node.path)
            else ""
        )
        self._popup_intent = ("rename", node.path)
        self._popup.open_at(
            self._anchor_for(node), "New name…", taken, initial=node.path[-1], note=note
        )

    def _on_name_chosen(self, name: str) -> None:
        intent, self._popup_intent = self._popup_intent, None
        if intent is None:
            return
        kind, path = intent
        if kind == "add":
            self.add_section_requested.emit(path, name)
        elif kind == "rename":
            self.rename_requested.emit(path, name)

    def _anchor_for(self, node: TreeNode) -> QPoint:
        """Global position for the popup: under *node*'s row, or the panel's
        top-left when the node has no row (the invisible root)."""
        model = self._view.model()
        if isinstance(model, BpxTreeModel):
            index = model.index_for_path(node.path)
            if index.isValid():
                rect = self._view.visualRect(index)
                return self._view.viewport().mapToGlobal(rect.bottomLeft())
        return self._view.viewport().mapToGlobal(QPoint(8, 8))


def _value_at(raw: object, path: tuple[str, ...]) -> object:
    """The raw value at *path*, or ``None`` when unreachable (defensive)."""
    node = raw
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node
