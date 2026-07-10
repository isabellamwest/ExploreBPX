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

from .values import values_equal


class EditorCard(QWidget):
    """Abstract value editor for a single :class:`ParameterItem`."""

    draft_changed = Signal()
    draft_reset = Signal()
    commit_requested = Signal()

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

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.KeyPress:
            # For combo boxes: pass Enter/Escape through when the popup is open
            # so that dropdown selection and dismissal work normally.
            try:
                from PySide6.QtWidgets import QComboBox  # local import avoids circularity
                if isinstance(obj, QComboBox) and obj.view().isVisible():
                    return super().eventFilter(obj, event)
            except Exception:
                pass

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

