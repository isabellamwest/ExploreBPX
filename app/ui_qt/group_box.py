"""Shared banded-header group box chrome.

One bordered, rounded frame whose first row is a shaded header band (caps
title, an optional suffix widget snug against it, an optional trailing
widget flush right past the stretch) over a body layout the caller fills
freely. This is the "IDE panel" language reused, previously, by three
independent copies: the Workspace document/reference cards, the
Diagnostics Issues/Outstanding boxes, and the reference-library dialog's
detail card. This module owns chrome only -- badges, content-hugging
lists and similar concerns stay in whichever module needs them, layered on
top via :attr:`GroupBox.body_layout` (or subclassing).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .titles import panel_title

#: The two visual variants, keyed to their QSS selectors in style.py: a
#: neutral grey band (Workspace's document card, Diagnostics' detail
#: boxes) or the reference purple band (docked-reference/reference-library
#: chrome). "reference" keeps its own historical object name since it
#: already carries its own purple QSS pair; "neutral" is the new shared
#: name that replaces the byte-identical WorkspaceGroupBox/
#: DiagnosticsGroupBox pair.
_FRAME_OBJECT_NAMES = {"neutral": "GroupBox", "reference": "ReferenceGroupBox"}
_HEADER_OBJECT_NAMES = {"neutral": "GroupBoxHeader", "reference": "ReferenceGroupBoxHeader"}


class GroupBox(QFrame):
    """One banded-header group box (see module docstring)."""

    def __init__(
        self,
        title: str,
        *,
        variant: str = "neutral",
        title_object_name: str = "PanelTitle",
        title_widget: QLabel | None = None,
        suffix: QWidget | None = None,
        trailing: QWidget | None = None,
        header_styled_background: bool = True,
        header_margins: tuple[int, int, int, int] = (12, 5, 12, 5),
        header_spacing: int | None = 8,
        body_margins: tuple[int, int, int, int] = (12, 10, 12, 12),
        body_spacing: int = 8,
        body_stretch: int = 0,
    ) -> None:
        """*suffix* sits immediately after the title, no stretch between
        them (Diagnostics' ratio text, e.g. "3 of 6"); *trailing* sits
        flush right, after the header's stretch (the reference card's
        "Read-only" tag, or Diagnostics' badge row). Both are optional and
        independent -- a caller can pass either, neither, or both.
        ``header_styled_background`` mirrors each call site's existing
        ``WA_StyledBackground`` use exactly (Diagnostics' header band never
        set it, so its migration passes ``False``, to keep rendering
        pixel-identical). ``header_spacing=None`` leaves Qt's own style
        default in place instead of forcing one (Diagnostics' original
        header never called ``setSpacing`` either). ``title_widget`` lets a
        caller supply its own pre-built label instead of the caps
        ``panel_title`` tier -- the reference-library dialog's detail
        heading is plain sentence-case text set later via ``setText``, not
        chrome the app itself titles, so it never went through
        ``panel_title``'s caps/letter-spacing treatment."""
        super().__init__()
        self.setObjectName(_FRAME_OBJECT_NAMES[variant])
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName(_HEADER_OBJECT_NAMES[variant])
        if header_styled_background:
            header.setAttribute(Qt.WA_StyledBackground, True)
        self.header_layout = QHBoxLayout(header)
        self.header_layout.setContentsMargins(*header_margins)
        if header_spacing is not None:
            self.header_layout.setSpacing(header_spacing)

        self.title_label = title_widget if title_widget is not None else panel_title(
            title, object_name=title_object_name
        )
        self.header_layout.addWidget(self.title_label)
        if suffix is not None:
            self.header_layout.addWidget(suffix)
        self.header_layout.addStretch(1)
        if trailing is not None:
            self.header_layout.addWidget(trailing)
        outer.addWidget(header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(*body_margins)
        self.body_layout.setSpacing(body_spacing)
        outer.addWidget(self.body, body_stretch)
