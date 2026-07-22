"""ReferenceValueBlock: the "Reference file" heading + read-only value row
shared by ``ParameterCard`` (its reference section, multi-file track M2/M3;
see ``ParameterCard.set_reference``) and ``GhostParameterCard`` (which shows
it unconditionally) -- one widget so the two can never drift apart.

Plain ``QLabel``s and a button only -- deliberately outside any editor's
draft/commit machinery (known Qt pitfall): populating it can never trip
``_touched``, since it wires no signal into an editor at all. The block owns
no identity of its own any more (the comparison strip owns the reference
filename); it shows only the value and a "Copy up" action.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..style import VALUE_INPUT_MAX_WIDTH

#: "No maximum": Qt's QWIDGETSIZE_MAX, restored when the row is not narrow.
_NO_MAX_WIDTH = 16777215


class ReferenceValueBlock(QFrame):
    """The "Reference file" heading plus its read-only value row: a purple-
    framed value box, an optional unit label (mirroring the main editor's
    own, for the kinds that show one), and a "Copy up" button."""

    #: Emitted when "Copy up" is clicked. Purely informational at this
    #: milestone -- the owning card re-exposes it verbatim; nothing wires it
    #: any further yet.
    copy_up_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReferenceBlock")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)

        self._heading = QLabel("Reference file")
        self._heading.setObjectName("ReferenceFileHeading")
        layout.addWidget(self._heading)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._value_box = QFrame()
        self._value_box.setObjectName("ReferenceValueBox")
        box_layout = QHBoxLayout(self._value_box)
        box_layout.setContentsMargins(8, 4, 8, 4)
        self._value = QLabel()
        self._value.setObjectName("ReferenceBlockValue")
        self._value.setWordWrap(True)
        box_layout.addWidget(self._value)
        row.addWidget(self._value_box, 1)

        #: Hidden by default -- shown only for the kinds whose main editor
        #: shows a unit label too (see ``set_content``).
        self._unit_label = QLabel()
        self._unit_label.setObjectName("ReferenceUnitLabel")
        self._unit_label.hide()
        row.addWidget(self._unit_label)

        # Zero-stretch spacer: inert while the (stretch-1) value box may grow,
        # but when the box is capped (*narrow*) it soaks up the slack so the
        # button keeps its natural width instead of inheriting the row's.
        row.addStretch(0)

        self._copy_up = QPushButton("Copy up")
        self._copy_up.setObjectName("CopyUpButton")
        self._copy_up.clicked.connect(self.copy_up_requested)
        row.addWidget(self._copy_up)

        layout.addLayout(row)

    def set_content(
        self, value_text: str, unit: str, same_as_main: bool, *, narrow: bool = False
    ) -> None:
        """Show the reference's *value_text* (and *unit*, if any).

        *same_as_main* (an EQUAL row) appends " · same" and renders the value
        in the faint "same" style rather than the loud one, and disables
        "Copy up" -- there is nothing to copy. An empty *unit* hides the unit
        label entirely, the same as the main editor's own unit label.

        *narrow* mirrors the main editor's input width (structured-page
        layout): the kinds whose main input is capped at
        ``VALUE_INPUT_MAX_WIDTH`` cap this box the same, so the two value
        columns align; every other kind's value (a series, a table preview)
        keeps the full row.
        """
        self._value_box.setMaximumWidth(
            VALUE_INPUT_MAX_WIDTH if narrow else _NO_MAX_WIDTH
        )
        self._value.setText(f"{value_text} · same" if same_as_main else value_text)
        self._value.setProperty("same", same_as_main)
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
        self._unit_label.setText(unit)
        self._unit_label.setVisible(bool(unit))
        self._copy_up.setEnabled(not same_as_main)
