"""Base class for editing cards.

A card edits a *draft* of one parameter value. It never touches the document;
it emits ``draft_changed`` while the user types (for live validation),
``draft_reset`` when the user discards a draft, and ``commit_requested`` when
the user presses Enter.

Keyboard contract (for editable cards):
- Enter / Return  → emit ``commit_requested`` (Inspector commits to document).
- Shift+Enter     → for cards that set ``accepts_multiline_input = True``
                    (e.g. ``TextCard``), insert a newline via
                    ``_insert_newline()`` instead of committing. Every other
                    card treats Shift+Enter the same as plain Enter, so the
                    app-wide commit contract is otherwise unchanged.
- Escape          → restore to original value, emit ``draft_reset`` (Inspector
                    restores the committed validation state immediately).

Cards register input widgets with ``_install_keyboard_handler`` in their
``__init__``. ``ReadOnlyCard`` does neither.

A card also exposes ``is_dirty``, which the Inspector uses to skip a no-op
commit (pressing Enter without editing anything). ``is_dirty`` is *not* a pure
value comparison: it first requires that the user actually touched the input.
A card's rendering of its value is not injective -- ``TextCard`` renders both
``None`` and ``""`` as an empty box -- so a stored ``null`` would otherwise
look like an edit to ``""`` the instant the card was built, and a bare Enter
would silently rewrite the document. Requiring a real interaction first, then
comparing values, keeps both halves honest (see ``values.values_equal``).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QWidget

from core.bpx_gateway import FieldMeta
from core.tree_model import ParameterItem
from core.values import values_equal


def _sub_editor_owns_keys(obj: QObject) -> bool:
    """Whether *obj* has an editor of its own open right now.

    While one is, Enter and Escape belong to it, not to the card: a combo
    box's popup uses them to pick and dismiss an entry, and an item view's
    cell editor uses them to confirm and cancel the cell. The card's filter
    must stand aside for both, or a keystroke aimed at the inner editor
    reaches the document.

    The item-view case is not hypothetical. Qt's delegate answers Enter by
    *queueing* the commit-and-close and returning False, so the key event
    keeps travelling -- editor, viewport, view -- and this filter, which
    sits on the view, sees it while the view is still in ``EditingState``.
    Without this guard a cell-level Enter committed the entire grid draft to
    the document, and the queued cell write then landed after the card had
    been rebuilt, losing the character just typed.
    """
    # Local imports: this module is imported by every card, and pulling the
    # widget classes in at module scope re-enters the cards package.
    from PySide6.QtWidgets import QAbstractItemView, QComboBox

    if isinstance(obj, QComboBox):
        return obj.view().isVisible()
    if isinstance(obj, QAbstractItemView):
        return obj.state() == QAbstractItemView.EditingState
    return False


class EditorCard(QWidget):
    """Abstract value editor for a single :class:`ParameterItem`."""

    draft_changed = Signal()
    draft_reset = Signal()
    commit_requested = Signal()
    #: Emitted with a ready-made :class:`core.commands.SetValues` when the
    #: user confirms an edit that spans *several* parameters (CSV import
    #: filling a Validation run's four arrays). Unlike ``commit_requested``,
    #: which asks the Inspector to commit this card's own draft, the payload
    #: here already names every path it writes; the Inspector executes it as
    #: one undoable command. Only cards that own such a flow ever emit it.
    bulk_commit_requested = Signal(object)

    #: Multi-line cards (e.g. ``TextCard``) set this True so Shift+Enter
    #: inserts a newline via ``_insert_newline`` instead of committing.
    accepts_multiline_input = False

    def __init__(self, parameter: ParameterItem, meta: FieldMeta | None) -> None:
        super().__init__()
        self.parameter = parameter
        self.meta = meta
        self._original = parameter.value
        # Set by any ``draft_changed`` emission, i.e. by real user
        # interaction: every card populates its input widget *before* wiring
        # that widget's change signal, so construction never marks a card
        # touched. Cleared again by ``_reset_draft`` (Escape).
        self._touched = False
        self.draft_changed.connect(self._mark_touched)

    def _mark_touched(self) -> None:
        self._touched = True

    def value(self) -> object:
        """Return the current draft value in raw-dict form."""
        raise NotImplementedError

    def reset(self) -> None:
        """Restore the editor to the original (last committed) value."""
        raise NotImplementedError

    def _insert_newline(self) -> None:
        """Insert a newline into the draft instead of committing.

        Only reachable when ``accepts_multiline_input`` is True; a multi-line
        card overrides this.
        """
        raise NotImplementedError

    def commit_blocked_reason(self) -> str | None:
        """Why this draft cannot be committed at all, or ``None`` to allow it.

        Almost always ``None``: a card emits raw input and never judges whether
        a value is *legal* -- the BPX validator owns that, and an invalid value
        must be committable so it can be seen and repaired.

        The exception is a draft with **no representation**. A Raw JSON editor
        holding unparseable text has no value to hand over at all; committing
        its text as a *string* would replace ``{"x": [...], "y": [...]}`` with
        a broken string. That is data loss, not an invalid edit, so the card
        refuses and explains why.
        """
        return None

    def commit_open_subeditor(self) -> None:
        """Commit any grid cell editor this card has open right now, as Enter
        would.

        A grid-bearing card's ``value()`` reads the grid's *model*, and an
        open cell editor's typed text lives only in the editor widget until
        Qt's delegate commits it -- normally on the cell's own Enter (see
        ``cards.grid._GridView``). ``InspectorPanel.apply_pending_draft``
        calls this before reading the draft, for a caller (Save, Export)
        that is not that Enter -- otherwise the last keystroke is silently
        missing from what gets read. A no-op for every card without a grid
        of its own; the two that have one (``SeriesCard``, ``ModalCard``)
        override it.
        """

    def growable_grid(self):
        """The one grid that should absorb the Inspector's leftover page
        height, or ``None`` for a card with nothing to grow.

        A grid is the only editor whose content can outrun its window, so it
        is the only one worth growing: the host hands the page's stretch to a
        grid with rows to spare (``NumericGrid.set_fill_available``), rather
        than leaving a table at eight rows above a slab of white. Cards
        without a grid keep the default ``None`` and the page keeps its white
        tail.
        """
        return None

    def set_cell_issues(self, issues) -> None:
        """Render the validator's per-cell diagnostics, if this card has cells.

        A no-op for most cards. A grid-bearing card maps *issues* onto the
        cells the validator blamed and tints them (see ``cell_issues``); the
        card never judges anything itself -- it renders exactly what it is
        told, so the validator stays the sole source of truth.
        """

    def set_reference_curves(self, curves) -> None:
        """Overlay one curve per pinned reference that has this key on this
        card's own live preview; an empty list clears the overlay.

        A no-op for every card whose editor is not table-shaped (most
        cards). Each ``table_preview.ReferenceCurve`` already carries the
        ``(x, y)`` pairs that reference's own grid would show
        (``bodies.table_rows``) -- this never re-parses a reference value
        itself. ``ParameterCard`` calls this whenever the pinned references
        change, independent of which mode a strip-based card currently
        shows.
        """

    def reference_value_width(self) -> int | None:
        """The width cap of this editor's value input, so an aligned
        read-only reference value can match it exactly -- or ``None`` when
        the editor takes the full row (grids, expressions, dropdowns) and
        the reference value should too."""
        return None

    @property
    def is_editable(self) -> bool:
        return True

    @property
    def is_dirty(self) -> bool:
        """Whether the user has edited this card into a genuinely new value.

        An untouched card is never dirty, whatever ``value()`` reports: a card
        that has not been interacted with cannot represent an intent to change
        anything. This is what protects a stored ``null`` in a text field,
        which renders -- and therefore reads back -- as ``""``.

        Once touched, the draft still has to *differ* from the original, so
        typing a value and retyping the same value again commits nothing.
        """
        return self._touched and not values_equal(self.value(), self._original)

    # ------------------------------------------------------------------
    # Keyboard handling helpers
    # ------------------------------------------------------------------

    def _install_keyboard_handler(self, widget: QWidget) -> None:
        """Watch *widget* for Enter (commit) and Escape (revert) key presses."""
        widget.installEventFilter(self)

    def _bind_grid_pending(self, grid) -> None:
        """Drive *grid*'s "Unsaved edits" bar from this card's dirty state.

        The bar is the visible face of the otherwise invisible draft: it
        shows exactly while ``is_dirty`` is true -- so an edit typed back to
        the original value hides it again -- and its buttons re-enter the
        keyboard paths verbatim (Apply is Enter, Discard is Esc). Nothing
        here needs to react to a successful commit: committing rebuilds the
        card (``MainWindow._on_committed`` → ``show_parameter``), so a fresh,
        clean card starts with the bar hidden.
        """
        grid.apply_clicked.connect(self.commit_requested)
        grid.discard_clicked.connect(self._reset_draft)

        def refresh() -> None:
            grid.set_pending(self.is_dirty)

        self.draft_changed.connect(refresh)
        self.draft_reset.connect(refresh)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.KeyPress:
            if _sub_editor_owns_keys(obj):
                return super().eventFilter(obj, event)

            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if self.accepts_multiline_input and event.modifiers() & Qt.ShiftModifier:
                    self._insert_newline()
                    return True
                self.commit_requested.emit()
                return True
            if key == Qt.Key_Escape:
                self._reset_draft()
                return True
        return super().eventFilter(obj, event)

    def _reset_draft(self) -> None:
        self.reset()
        # After, not before: ``reset()`` repopulates the input widget, which
        # re-emits ``draft_changed`` and would otherwise leave the card marked
        # touched -- so a reverted card would still look dirty to the
        # Inspector and a following Enter would commit it.
        self._touched = False
        self.draft_reset.emit()

