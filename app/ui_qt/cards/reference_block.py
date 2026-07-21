"""ReferenceValueBlock: the purple-framed, read-only block a ``ParameterCard``
shows below its own content for the docked reference's value (multi-file
track M2/M3; see ``ParameterCard.set_reference``).

Plain ``QLabel``s only -- deliberately outside the card's draft/commit
machinery (known Qt pitfall): populating it can never trip ``_touched``,
since it wires no signal into the editor at all.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class ReferenceValueBlock(QFrame):
    """Subordinate, read-only display of the reference's value for the
    parameter the editing card above it is showing."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReferenceBlock")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._heading = QLabel()
        self._heading.setObjectName("ReferenceBlockHeading")
        layout.addWidget(self._heading)

        self._value = QLabel()
        self._value.setObjectName("ReferenceBlockValue")
        self._value.setWordWrap(True)
        layout.addWidget(self._value)

    def set_content(self, filename: str, value_text: str, same_as_main: bool) -> None:
        """Show *filename*'s reference value; *same_as_main* renders it in
        the faint "same" style (an EQUAL row) rather than the loud one."""
        self._heading.setText(f"◇ {filename}")
        self._value.setText(value_text)
        self._value.setProperty("same", same_as_main)
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
