"""ParameterCard: self-contained composition of one parameter's work surface.

Top to bottom, a ``ParameterCard`` holds:

  1. a header (title label + validity badge + ( i ) information button that
     toggles a :class:`~ui_qt.parameter_info_popover.ParameterInfoPopover` —
     the quick glance; the long-form prose lives in the Inspector's
     Documentation tab),
  2. the per-kind value editor, produced by :func:`create_card`,
  3. the parameter's summary description, when present.

``ParameterCard`` is a pure composition container. It forwards the inner
editor's ``draft_changed`` / ``draft_reset`` / ``commit_requested`` signals
unchanged and re-exposes ``parameter``, ``value()``, ``reset()`` and
``is_dirty`` so callers can treat it like the editor it wraps. It does not
decide validity: the badge is driven externally via :meth:`set_validity`, and
all validation orchestration stays in ``InspectorPanel``.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from core.bpx_gateway import FieldMeta
from core.parameter_metadata import resolve_parameter_metadata
from core.tree_model import ParameterItem

from ..parameter_info_popover import ParameterInfoPopover
from .registry import create_card


class ParameterCard(QWidget):
    """Composes the header, per-kind editor and description for one parameter."""

    draft_changed = Signal()
    draft_reset = Signal()
    commit_requested = Signal()

    def __init__(self, parameter: ParameterItem, meta: FieldMeta | None) -> None:
        super().__init__()
        self.parameter = parameter
        self._meta = meta
        self._popover: ParameterInfoPopover | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self._title = QLabel(parameter.label)
        self._title.setObjectName("CardTitle")
        header.addWidget(self._title, 1)
        self._badge = QLabel("")
        header.addWidget(self._badge)
        self._info_button = QPushButton("i")
        self._info_button.setObjectName("InfoButton")
        self._info_button.setToolTip("Parameter information")
        self._info_button.setFixedSize(20, 20)
        self._info_button.setStyleSheet(
            "border-radius: 10px; font-style: italic; font-weight: 600;"
        )
        self._info_button.clicked.connect(self._toggle_info_popover)
        header.addWidget(self._info_button)
        layout.addLayout(header)

        self._editor = create_card(parameter, meta)
        self._editor.draft_changed.connect(self.draft_changed)
        self._editor.draft_reset.connect(self.draft_reset)
        self._editor.commit_requested.connect(self.commit_requested)
        # Value row: the editor plus a trailing slot. The trailing slot is
        # reserved -- not built -- for a future Reference document's value
        # and delta once multi-document lands (docs/03-features.md §4); no
        # widget or API for it exists yet, so today's layout is visually
        # identical to the editor sitting alone.
        value_row = QHBoxLayout()
        value_row.addWidget(self._editor, 1)
        layout.addLayout(value_row)

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

    @property
    def is_dirty(self) -> bool:
        """Whether the inner editor's draft differs from its original value."""
        return self._editor.is_dirty

    def commit_blocked_reason(self) -> str | None:
        """Why the inner editor's draft has no representation, if it has none."""
        return self._editor.commit_blocked_reason()

    def set_validity(self, text: str, colour: str) -> None:
        """Drive the header badge; validity decisions stay in the Inspector."""
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"color: white; background: {colour}; padding: 2px 8px; border-radius: 3px;"
        )

    def _toggle_info_popover(self) -> None:
        """Open the info popover on the first click, close it on the second."""
        if self._popover is not None and self._popover.isVisible():
            self._popover.hide()
            return
        if self._popover is None:
            self._popover = ParameterInfoPopover(self)
        metadata = resolve_parameter_metadata(self.parameter.path, self._meta)
        self._popover.show_metadata(metadata)
        self._popover.open_below(self._info_button)
