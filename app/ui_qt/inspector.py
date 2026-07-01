"""Inspector (right panel): the single editor surface for one parameter.

Layout: title + validity badge, then a value editor (per-kind card) followed by
an optional description.  Editing uses a draft buffer: typing validates a
candidate dict live (badge updates).  Commit is driven by Enter or the inline
Reset interaction within the card; there are no detached Apply/Reset buttons.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import bpx_gateway
from core.tree_model import ParameterItem
from core.validation import Severity
from state.app_state import AppState

from .cards.registry import create_card
from .style import ERROR, OK, WARNING


class InspectorPanel(QWidget):
    """Hosts the editing card for the selected parameter."""

    committed = Signal()

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._card = None
        self._debounce = QTimer(self, singleShot=True, interval=200)
        self._debounce.timeout.connect(self._validate_draft)
        self._build()
        self.show_placeholder()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self._title = QLabel("")
        self._title.setObjectName("CardTitle")
        self._badge = QLabel("")
        header.addWidget(self._title, 1)
        header.addWidget(self._badge)
        outer.addLayout(header)

        body = QHBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        scroll.setWidget(self._content)
        body.addWidget(scroll)
        outer.addLayout(body, 1)

    def show_placeholder(self) -> None:
        self._clear_content()
        self._title.setText("")
        self._badge.setText("")
        self._content_layout.addWidget(
            QLabel("Select an object from the structure to inspect + edit it.")
        )

    def show_parameter(self, parameter: ParameterItem) -> None:
        self._clear_content()
        meta = bpx_gateway.metadata_index().get(parameter.label)
        self._title.setText(parameter.label)

        self._card = create_card(parameter, meta)
        self._card.draft_changed.connect(self._debounce.start)
        self._card.commit_requested.connect(self._on_commit)
        self._content_layout.addWidget(self._card)

        if parameter.description:
            self._content_layout.addWidget(QLabel("Description:", objectName="Heading"))
            desc = QTextEdit(parameter.description)
            desc.setReadOnly(True)
            desc.setMaximumHeight(120)
            self._content_layout.addWidget(desc)

        self._content_layout.addStretch(1)
        self._render_issues(parameter.issues, parameter.has_errors)

    def _validate_draft(self) -> None:
        if self._card is None or self._state.active is None:
            return
        result = self._state.active.preview_value(self._card.parameter.path, self._card.value())
        errors = [i for i in result.issues if i.severity == Severity.ERROR]
        self._render_issues(result.issues, bool(errors))

    def _on_commit(self) -> None:
        if self._card is None or self._state.active is None:
            return
        self._state.active.apply_value(self._card.parameter.path, self._card.value())
        self.committed.emit()

    def _render_issues(self, issues, has_errors: bool) -> None:
        if not issues:
            self._set_badge("Valid", OK)
            return
        self._set_badge("Invalid" if has_errors else "Warning", ERROR if has_errors else WARNING)

    def _set_badge(self, text: str, colour: str) -> None:
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"color: white; background: {colour}; padding: 2px 8px; border-radius: 3px;"
        )

    def _clear_content(self) -> None:
        self._card = None
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
