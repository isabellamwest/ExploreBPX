"""Shared rich-text row rendering for parameter lists.

Both the add-parameter popup (:mod:`ui_qt.add_parameter_popup`) and the
parameter-list pane (:mod:`ui_qt.parameter_list`) render one row the same
way: a bold parameter *name*, coloured by role (required / suggested /
plain), followed by non-bold, muted trailing text (a unit, a kind hint, a
"Required" tag, a validator marker). Composing that rich-text fragment and
painting it -- word-wrapped rather than elided, so a long alias is never cut
off -- lives here once, so the two surfaces' rendering never diverges.

Callers build the HTML fragment (via :func:`compose_row_html` or a small
caller-specific helper) and stash it under :data:`HTML_ROLE`; a row that
carries no such data (a group header, in the popup) is left to
``QStyledItemDelegate``'s normal single-line painting, unchanged.
"""

from __future__ import annotations

import html as _html

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from core.parameter_types import extract_unit
from ui_qt import style

#: Item-data role carrying the HTML fragment :class:`ParameterRowDelegate`
#: paints. A row without it (e.g. a group header) falls back to the base
#: ``QStyledItemDelegate`` behaviour untouched.
HTML_ROLE = Qt.UserRole + 100

#: The app's default (untinted) text colour -- matches the base ``QWidget``
#: rule in this module's stylesheet (``ui_qt/style.py``); named here so a
#: "plain" row's name can be coloured explicitly, the same as every other
#: tier, rather than left to whatever the delegate happens to inherit.
DEFAULT_TEXT = "#1f2328"

_MIN_WIDTH = 40


def split_name_and_unit(label: str) -> tuple[str, str]:
    """Split a trailing-unit BPX label (``"Thickness [m]"``) into its bare
    name and unit, using the same trailing-bracket convention as
    :func:`core.parameter_types.extract_unit`. A label with no unit suffix
    returns it unchanged, with an empty unit."""
    unit = extract_unit(label)
    if not unit:
        return label, ""
    idx = label.rfind("[")
    name = label[:idx].rstrip() if idx != -1 else label
    return name, unit


def _span(text: str, *, color: str, bold: bool = False) -> str:
    weight = 600 if bold else 400
    return f'<span style="font-weight:{weight}; color:{color};">{_html.escape(text)}</span>'


def compose_row_html(name: str, hints: list[tuple[str, str]], *, name_color: str) -> str:
    """Compose a row's rich-text fragment: bold *name* in *name_color*,
    followed by a muted, parenthesised, " · "-joined *hints* list -- each
    hint an ``(text, color)`` pair, so one tag (e.g. "Required") can carry a
    colour distinct from its neighbours."""
    fragment = _span(name, color=name_color, bold=True)
    if hints:
        dot = _span(" · ", color=style.MUTED)
        joined = dot.join(_span(text, color=color) for text, color in hints)
        fragment += _span("  (", color=style.MUTED) + joined + _span(")", color=style.MUTED)
    return fragment


def build_parameter_row_html(label: str, *, has_errors: bool, is_empty: bool = False) -> str:
    """Compose a parameter-list row's rich-text fragment: bold name, a muted
    non-bold unit, and -- for a parameter with a *page-visible* issue -- an
    ``style.ERROR``-coloured "⚠" marker.

    ``has_errors`` means *page-visible* (decision P), not validator-verbatim:
    the caller passes whether this parameter has an issue that survived
    absorption (``core.completion.partition_issues``'s ``visible``), not
    ``parameter.has_errors``. The card's own inline badge and the Issues tab
    still mirror the validator verbatim (decision D) -- only this row marker's
    meaning changed.

    ``is_empty`` (a committed ``null`` value) renders the name/unit muted
    instead of the normal text colour -- emptiness visible at a glance,
    covering both "never filled" and "value was removed" (indistinguishable
    in a stateless projection over the raw dict).

    The list deliberately carries **no requiredness colouring**: the
    required/suggested tint is the *add-parameter popup's* language, for
    choosing a field that isn't there yet. A parameter in this list is already
    present, so colouring it by requiredness would tint most of a document
    amber for no actionable reason."""
    name, unit = split_name_and_unit(label)
    name_color = style.MUTED if is_empty else DEFAULT_TEXT
    fragment = _span(name, color=name_color, bold=True)
    if unit:
        fragment += _span(f" [{unit}]", color=style.MUTED)
    if has_errors:
        fragment += _span("  ⚠", color=style.ERROR)
    return fragment


class ParameterRowDelegate(QStyledItemDelegate):
    """Paints a row's :data:`HTML_ROLE` fragment via ``QTextDocument``,
    word-wrapped to the view's available width rather than elided.

    A row with no ``HTML_ROLE`` data (a group header) is painted by the base
    ``QStyledItemDelegate`` untouched, so header rows keep their existing
    look. *h_pad*/*v_pad* are the row's own padding, matching whichever
    list's stylesheet ``::item`` rule this delegate paints for -- picked
    explicitly rather than read back from the stylesheet at paint time,
    since the item rect (not the ``::item``-adjusted sub-rect) is what
    ``sizeHint`` can reliably reason about before the row exists on screen.
    """

    def __init__(self, parent=None, *, h_pad: int = 8, v_pad: int = 6) -> None:
        super().__init__(parent)
        self._h_pad = h_pad
        self._v_pad = v_pad

    def _available_width(self, option: QStyleOptionViewItem) -> float:
        widget = option.widget
        if widget is not None and hasattr(widget, "viewport"):
            width = widget.viewport().width()
        elif option.rect.width() > 0:
            width = option.rect.width()
        else:
            width = 300
        return max(width, _MIN_WIDTH)

    def _build_document(
        self, option: QStyleOptionViewItem, index, text_width: float
    ) -> QTextDocument | None:
        html = index.data(HTML_ROLE)
        if html is None:
            return None
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(option.font)
        doc.setHtml(html)
        doc.setTextWidth(max(text_width, _MIN_WIDTH))
        return doc

    def sizeHint(self, option, index):
        width = self._available_width(option)
        doc = self._build_document(option, index, width - 2 * self._h_pad)
        if doc is None:
            return super().sizeHint(option, index)
        return QSize(int(width), int(doc.size().height()) + 2 * self._v_pad)

    def paint(self, painter, option, index) -> None:
        row_width = option.rect.width() if option.rect.width() > 0 else self._available_width(option)
        doc = self._build_document(option, index, row_width - 2 * self._h_pad)
        if doc is None:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style_obj = widget.style() if widget is not None else QApplication.style()
        style_obj.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)

        painter.save()
        painter.translate(option.rect.left() + self._h_pad, option.rect.top() + self._v_pad)
        doc.drawContents(painter)
        painter.restore()
