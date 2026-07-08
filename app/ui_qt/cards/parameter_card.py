"""ParameterCard: self-contained composition of one parameter's work surface.

Top to bottom, a ``ParameterCard`` holds:

  1. a header (title label + validity badge; a slot is reserved for a future
     ( i ) information button - see roadmap 2.4 sub-step 2 - but no button is
     added yet),
  2. the per-kind value editor, produced by :func:`create_card`,
  3. the parameter's summary description, when present.

``ParameterCard`` is a pure composition container. It forwards the inner
editor's ``draft_changed`` / ``draft_reset`` / ``commit_requested`` signals
unchanged and re-exposes ``parameter``, ``value()`` and ``reset()`` so callers
can treat it like the editor it wraps. It does not decide validity: the badge
is driven externally via :meth:`set_validity`, and all validation orchestration
stays in ``InspectorPanel``.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget

from core.bpx_gateway import FieldMeta
from core.tree_model import ParameterItem

from .registry import create_card


class ParameterCard(QWidget):
    """Composes the header, per-kind editor and description for one parameter."""

    draft_changed = Signal()
    draft_reset = Signal()
    commit_requested = Signal()

    def __init__(self, parameter: ParameterItem, meta: FieldMeta | None) -> None:
        super().__init__()
        self.parameter = parameter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self._title = QLabel(parameter.label)
        self._title.setObjectName("CardTitle")
        header.addWidget(self._title, 1)
        self._badge = QLabel("")
        header.addWidget(self._badge)
        # Reserved slot: a future ( i ) info button is added after the badge
        # (roadmap 2.4 sub-step 2).
        layout.addLayout(header)

        self._editor = create_card(parameter, meta)
        self._editor.draft_changed.connect(self.draft_changed)
        self._editor.draft_reset.connect(self.draft_reset)
        self._editor.commit_requested.connect(self.commit_requested)
        layout.addWidget(self._editor)

        if parameter.description:
            layout.addWidget(QLabel("Description:", objectName="Heading"))
            desc = QTextEdit(parameter.description)
            desc.setReadOnly(True)
            desc.setMaximumHeight(120)
            layout.addWidget(desc)

    def value(self) -> object:
        """Return the inner editor's current draft value in raw-dict form."""
        return self._editor.value()

    def reset(self) -> None:
        """Restore the inner editor to the original (last committed) value."""
        self._editor.reset()

    @property
    def is_editable(self) -> bool:
        return self._editor.is_editable

    def set_validity(self, text: str, colour: str) -> None:
        """Drive the header badge; validity decisions stay in the Inspector."""
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"color: white; background: {colour}; padding: 2px 8px; border-radius: 3px;"
        )
