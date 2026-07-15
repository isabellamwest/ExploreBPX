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
import json

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from core.parameter_types import ParameterKind, extract_unit, looks_like_table
from ui_qt import style

#: Item-data role carrying the HTML fragment :class:`ParameterRowDelegate`
#: paints. A row without it (e.g. a group header) falls back to the base
#: ``QStyledItemDelegate`` behaviour untouched.
HTML_ROLE = Qt.UserRole + 100
#: Item-data role carrying a row's right-aligned value-preview string; the
#: delegate elides it with "…" against the space the name leaves free, so a
#: 20-decimal float never wraps or pushes the name around. Absent on rows
#: with no value column (group headers, suggestion rows, other lists).
VALUE_ROLE = Qt.UserRole + 101
#: Companion flag: True renders the preview ghosted (lighter, italic) --
#: the "—" of a committed null and the derived summaries of Inspector-only
#: kinds ("table · 3 points"), as opposed to a verbatim raw value.
VALUE_GHOST_ROLE = Qt.UserRole + 102

#: The app's default (untinted) text colour -- matches the base ``QWidget``
#: rule in this module's stylesheet (``ui_qt/style.py``); named here so a
#: "plain" row's name can be coloured explicitly, the same as every other
#: tier, rather than left to whatever the delegate happens to inherit.
DEFAULT_TEXT = "#1f2328"
#: Ghosted value-preview text (matches the disabled-button foreground in
#: the stylesheet): quieter than ``style.MUTED`` so a placeholder reads as
#: "nothing here", not as a value.
GHOST_TEXT = "#8c959f"

_MIN_WIDTH = 40
#: The value preview never claims more than this share of the row, however
#: long the raw value is -- the name keeps priority, the value elides.
_VALUE_MAX_SHARE = 0.45
#: Gap between the (wrapped) name fragment and the value preview.
_VALUE_GAP = 12


def value_preview(value: object, kind: ParameterKind) -> tuple[str, bool]:
    """Return ``(text, ghost)`` for a parameter row's value column.

    Simple committed values render **verbatim from the raw document** (JSON
    spelling for numbers and booleans, the bare string for text) -- never
    reformatted, rounded or re-spelled, per validator fidelity. Committed
    ``null`` renders as a ghosted "—" (the muted-emptiness language of
    decision P). Inspector-only kinds render a ghosted summary *derived*
    from the data (point/entry/value counts), never invented content.
    Elision to the available width is the delegate's job, not this one's:
    the full string is returned so tooltips can carry it.
    """
    if value is None:
        return "—", True
    if isinstance(value, bool):
        return ("true" if value else "false"), False
    if isinstance(value, (int, float)):
        return json.dumps(value), False
    if isinstance(value, str):
        first, sep, _rest = value.partition("\n")
        return (first + "…" if sep else first), False
    if isinstance(value, dict):
        if looks_like_table(value):
            count = len(value["x"])
            return f"table · {count} point{'s' if count != 1 else ''}", True
        count = len(value)
        return f"{count} entr{'ies' if count != 1 else 'y'}", True
    if isinstance(value, list):
        noun = "series" if kind is ParameterKind.SERIES else "list"
        count = len(value)
        return f"{noun} · {count} value{'s' if count != 1 else ''}", True
    return str(value), False


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


#: Tooltip cap: enough to read a long mantissa or expression in full, short
#: enough that a 1000-point table doesn't become a screen-filling tooltip.
_TOOLTIP_MAX = 400


def value_tooltip(value: object) -> str:
    """The full committed value as compact JSON (strings verbatim), capped
    at ``_TOOLTIP_MAX`` characters with an explicit ellipsis."""
    text = value if isinstance(value, str) else json.dumps(value)
    if len(text) > _TOOLTIP_MAX:
        return text[: _TOOLTIP_MAX - 1] + "…"
    return text


def compose_issue_row_html(
    severity_label: str, severity_color: str, location: str, message: str
) -> str:
    """Compose an issue row as **two lines**: a coloured severity tag and the
    bold location on the first, the validator's verbatim message (muted,
    smaller) on the second.

    Splitting where (location) from what (message) is Concept A's core move --
    a full-width run-on sentence per issue becomes a scannable header with its
    detail beneath. Shared by the Validation page's Issues section and the
    Inspector's Issues tab so the two issue surfaces read as one system; the
    tab passes an empty *location* (it is already scoped to one parameter),
    which drops the row to tag-over-message. *location* is expected already
    section-relative (the owning section is the group header above the row),
    and its trailing unit is muted like every other parameter label."""
    if location:
        name, unit = split_name_and_unit(location)
        head = _span(severity_label, color=severity_color, bold=True) + _span(
            "  " + name, color=DEFAULT_TEXT, bold=True
        )
        if unit:
            head += _span(f" [{unit}]", color=style.MUTED)
    else:
        head = _span(severity_label, color=severity_color, bold=True)
    detail = (
        f'<span style="color:{style.MUTED}; font-size:92%;">'
        f"{_html.escape(message)}</span>"
    )
    return head + "<br>" + detail


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

    def _value_font(self, option: QStyleOptionViewItem) -> QFont:
        """The value preview's font: the system fixed-pitch face, one step
        smaller than the row -- digits align across rows and a long mantissa
        reads as data rather than prose. The app stylesheet sizes fonts in
        pixels (``font-size: 13px``), which leaves ``pointSizeF()`` at -1,
        so size must follow whichever unit the row font actually carries."""
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        if option.font.pointSizeF() > 0:
            font.setPointSizeF(max(option.font.pointSizeF() - 1.0, 9.0))
        else:
            font.setPixelSize(max(option.font.pixelSize() - 1, 11))
        return font

    def _value_reserved(self, option: QStyleOptionViewItem, index, row_width: float) -> int:
        """Row width the value preview claims (including its gap), 0 when the
        row carries none. Capped at ``_VALUE_MAX_SHARE`` of the row: the name
        keeps priority and an overlong value elides rather than pushing it."""
        text = index.data(VALUE_ROLE)
        if not text:
            return 0
        metrics = QFontMetrics(self._value_font(option))
        # +1: elidedText is conservative at exact-fit width and would turn
        # "299.0" into "299…" inside space it actually fits.
        needed = metrics.horizontalAdvance(text) + 1
        return min(needed, int(row_width * _VALUE_MAX_SHARE)) + _VALUE_GAP

    def sizeHint(self, option, index):
        width = self._available_width(option)
        reserved = self._value_reserved(option, index, width)
        doc = self._build_document(option, index, width - 2 * self._h_pad - reserved)
        if doc is None:
            return super().sizeHint(option, index)
        return QSize(int(width), int(doc.size().height()) + 2 * self._v_pad)

    def paint(self, painter, option, index) -> None:
        row_width = option.rect.width() if option.rect.width() > 0 else self._available_width(option)
        reserved = self._value_reserved(option, index, row_width)
        doc = self._build_document(option, index, row_width - 2 * self._h_pad - reserved)
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

        if reserved:
            self._paint_value(painter, option, index, reserved)

    def _paint_value(self, painter, option, index, reserved: int) -> None:
        """Right-aligned, top-anchored value preview, elided with "…" to the
        reserved width -- elision is visual only; the full string travels on
        the item's tooltip."""
        font = self._value_font(option)
        ghost = bool(index.data(VALUE_GHOST_ROLE))
        if ghost:
            font.setItalic(True)
        metrics = QFontMetrics(font)
        elided = metrics.elidedText(
            index.data(VALUE_ROLE), Qt.ElideRight, reserved - _VALUE_GAP
        )
        painter.save()
        painter.setFont(font)
        painter.setPen(QColor(GHOST_TEXT if ghost else style.MUTED))
        rect = option.rect.adjusted(0, self._v_pad, -self._h_pad, -self._v_pad)
        painter.drawText(rect, Qt.AlignRight | Qt.AlignTop, elided)
        painter.restore()
