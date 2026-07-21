"""GhostParameterCard: the Inspector's read-only card for a selected REF_ONLY
row (multi-file track M2) -- a parameter the docked reference has and the
main document does not.

No draft, no input widget, no actions (the "↑ Copy up" pull button is a
later milestone): just the parameter's name and the reference's own value.
Mirrors ``ValidationEmptyState``'s "never dirty" contract (a class-level
``is_dirty``/``is_editable``) so the Inspector's undo guard and driver reads
treat it the same as any other non-``ParameterCard`` card.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.parameter_types import ParameterKind, split_name_and_unit

from ..parameter_row import value_preview


class GhostParameterCard(QWidget):
    """Purely informational: no draft, no commit, no context menu."""

    #: See the module docstring: this card holds no editable draft, so the
    #: Inspector's undo guard (``has_focused_draft``, which checks
    #: ``card.is_dirty`` on whatever ``_card`` currently is) always reads it
    #: as having nothing to lose.
    is_dirty = False
    is_editable = False

    def __init__(
        self, key: str, ref_value: object, kind: ParameterKind, reference_filename: str
    ) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._heading = QLabel("Not in the main file")
        self._heading.setObjectName("GhostCardHeading")
        layout.addWidget(self._heading)

        name, unit = split_name_and_unit(key)
        self._title = QLabel(f"{name} [{unit}]" if unit else name)
        self._title.setObjectName("CardTitle")
        layout.addWidget(self._title)

        text, ghost = value_preview(ref_value, kind)
        self._value = QLabel(f"◇ {reference_filename}: {text}")
        self._value.setObjectName("GhostCardValue")
        self._value.setWordWrap(True)
        if ghost:
            self._value.setStyleSheet("font-style: italic;")
        layout.addWidget(self._value)

        layout.addStretch(1)
