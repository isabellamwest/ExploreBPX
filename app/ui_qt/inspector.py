"""Inspector (right panel): the single editor surface for one parameter.

Layout mirrors the wireframe: title + validity badge, a value editor (per-kind
card), description, a deferred Display placeholder, an Issues pane, and
Reset/Apply. Editing uses a draft buffer: typing validates a candidate dict
live (badge + Issues update), and Apply commits to the document.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
        body.addWidget(scroll, 2)

        self._issues = QFrame(objectName="IssuesPane")
        issues_layout = QVBoxLayout(self._issues)
        issues_layout.addWidget(QLabel("Issues:", objectName="Heading"))
        self._issues_text = QLabel("None")
        self._issues_text.setWordWrap(True)
        issues_layout.addWidget(self._issues_text)
        issues_layout.addStretch(1)
        body.addWidget(self._issues, 1)
        outer.addLayout(body, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self._reset_btn = QPushButton("Reset")
        self._apply_btn = QPushButton("Apply")
        self._reset_btn.clicked.connect(self._on_reset)
        self._apply_btn.clicked.connect(self._on_apply)
        footer.addWidget(self._reset_btn)
        footer.addWidget(self._apply_btn)
        outer.addLayout(footer)

    def show_placeholder(self) -> None:
        self._clear_content()
        self._title.setText("")
        self._badge.setText("")
        self._issues_text.setText("None")
        self._reset_btn.setEnabled(False)
        self._apply_btn.setEnabled(False)
        self._content_layout.addWidget(
            QLabel("Select an object from the structure to inspect + edit it.")
        )

    def show_parameter(self, parameter: ParameterItem) -> None:
        self._clear_content()
        meta = bpx_gateway.metadata_index().get(parameter.label)
        self._title.setText(parameter.label)

        self._card = create_card(parameter, meta)
        self._card.draft_changed.connect(self._debounce.start)
        self._content_layout.addWidget(self._card)

        if parameter.description:
            self._content_layout.addWidget(QLabel("Description:", objectName="Heading"))
            desc = QTextEdit(parameter.description)
            desc.setReadOnly(True)
            desc.setMaximumHeight(120)
            self._content_layout.addWidget(desc)

        self._content_layout.addStretch(1)
        self._reset_btn.setEnabled(self._card.is_editable)
        self._apply_btn.setEnabled(self._card.is_editable)
        self._render_issues(parameter.issues, parameter.has_errors)

    def _validate_draft(self) -> None:
        if self._card is None:
            return
        result = self._state.preview_value(self._card.parameter.path, self._card.value())
        errors = [i for i in result.issues if i.severity == Severity.ERROR]
        self._render_issues(result.issues, bool(errors))

    def _on_reset(self) -> None:
        if self._card is not None:
            self._card.reset()
            self._validate_draft()

    def _on_apply(self) -> None:
        if self._card is None:
            return
        self._state.apply_value(self._card.parameter.path, self._card.value())
        self.committed.emit()

    def _render_issues(self, issues, has_errors: bool) -> None:
        if not issues:
            self._set_badge("Valid", OK)
            self._issues_text.setText("None")
            return
        self._set_badge("Invalid" if has_errors else "Warning", ERROR if has_errors else WARNING)
        self._issues_text.setText("\n\n".join(i.message for i in issues))

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
