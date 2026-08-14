"""A small anchored popup asking for one name (new material/experiment, rename).

The tree's creation and rename flows need exactly one string. This is the
lightest surface consistent with the app's creation UX: a frameless card
anchored at the tree row (like :class:`~ui_qt.add_parameter_popup.AddParameterPopup`,
whose visual style it shares), Enter confirms, Escape or an outside click
dismisses. Nothing touches the document here -- the popup emits the chosen name
and the window turns it into a command.

The one gate it owns is *representability of the intent*: an empty name names
nothing, and a sibling's name cannot be taken (an add would overwrite the
sibling; a rename is a move, never a merge). Both block Enter with the reason
shown inline -- the same refuse-and-explain convention as the duplicate-key
grid and the CSV mapping dialog. Whether a name is *legal* BPX stays the
validator's business.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QWidget,
)

from . import typography
from .dismissal import OutsideDismissFilter
from .floating_card import SHADOW_MARGIN as _SHADOW_MARGIN
from .floating_card import floating_card
from .style import ERROR, MUTED

_CARD_WIDTH = 300


class _NameInput(QLineEdit):
    """Keeps Enter/Escape local to the popup."""

    confirm_requested = Signal()
    escape_requested = Signal()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.confirm_requested.emit()
            return
        if key == Qt.Key_Escape:
            self.escape_requested.emit()
            return
        super().keyPressEvent(event)


class NamePopup(QWidget):
    """Frameless one-field popup; emits ``name_chosen`` with the trimmed name."""

    name_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NamePopup")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedWidth(_CARD_WIDTH + 2 * _SHADOW_MARGIN)
        self._dismiss_filter = OutsideDismissFilter(self)
        self._taken: frozenset[str] = frozenset()
        self._initial: str = ""

        # The AddParameter* object names deliberately reuse that popup's QSS:
        # the two surfaces are siblings in the creation UX and must not drift.
        self._input = _NameInput()
        self._input.setObjectName("AddParameterInput")
        self._input.textChanged.connect(self._refresh_gate)
        self._input.confirm_requested.connect(self._confirm)
        self._input.escape_requested.connect(self.hide)

        # A small, plain, informational note about *what renaming here means*
        # -- e.g. that a Particle material's old name stays behind in any
        # per-material reference (decision: UI copy only, no validation logic
        # here -- see ``core.structure.is_particle_material``). Muted, not
        # error-coloured: unlike ``_reason`` it never blocks Enter.
        self._note = QLabel("")
        self._note.setObjectName("NamePopupNote")
        self._note.setStyleSheet(f"color: {MUTED}; padding: 2px 4px 4px 4px; {typography.size_qss(typography.META)}")
        self._note.setWordWrap(True)
        self._note.hide()

        self._reason = QLabel("")
        self._reason.setObjectName("NamePopupReason")
        self._reason.setStyleSheet(f"color: {ERROR}; padding: 2px 4px 4px 4px; {typography.size_qss(typography.META)}")
        self._reason.setWordWrap(True)
        self._reason.hide()

        _, card_layout = floating_card(self, "AddParameterCard", width=_CARD_WIDTH)
        card_layout.addWidget(self._input)
        card_layout.addWidget(self._note)
        card_layout.addWidget(self._reason)

    # -- opening -------------------------------------------------------
    def open_at(
        self,
        global_pos: QPoint,
        placeholder: str,
        taken: frozenset[str] = frozenset(),
        initial: str = "",
        note: str = "",
    ) -> None:
        """Show the popup with its card's top-left at *global_pos*.

        *taken* is the set of sibling names that must not be chosen (an add
        would overwrite the sibling; a rename would merge into it). *initial*
        pre-fills (and selects) the current name so a rename starts from what
        is being renamed; re-confirming it unchanged is not a rename, so Enter
        then simply does nothing -- no red warning for a name the user has not
        even edited yet. *note*, when given, shows one small plain line under
        the input for the whole time the popup is open (e.g. the Particle
        rename note); empty by default, and cleared by every subsequent call
        that doesn't repeat it.
        """
        self._taken = frozenset(taken)
        self._initial = initial.strip()
        self._input.setPlaceholderText(placeholder)
        self._input.setText(initial)
        self._input.selectAll()
        self._note.setText(note)
        self._note.setVisible(bool(note))
        self._refresh_gate()
        self.move(global_pos - QPoint(_SHADOW_MARGIN, _SHADOW_MARGIN))
        self.show()
        self._dismiss_filter.install()
        self._input.setFocus(Qt.PopupFocusReason)

    # -- gate ----------------------------------------------------------
    def _blocked_reason(self) -> str | None:
        name = self._input.text().strip()
        if not name:
            return None  # nothing typed yet: no nagging, Enter just does nothing
        if name == self._initial:
            return None  # unchanged rename: a no-op, not an error
        if name in self._taken:
            return "This name is already used here."
        return None

    def _refresh_gate(self, *_args) -> None:
        reason = self._blocked_reason()
        self._reason.setVisible(reason is not None)
        self._reason.setText(reason or "")

    def _confirm(self) -> None:
        name = self._input.text().strip()
        if not name or name == self._initial or self._blocked_reason() is not None:
            return
        self.hide()
        self.name_chosen.emit(name)
