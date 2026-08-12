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

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from core.parameter_types import ParameterKind, looks_like_table
# split_name_and_unit lives in core.parameter_types (also used outside ui_qt,
# e.g. core.editing); re-exported here so existing ``parameter_row.``
# call sites (this module's own rows, the add-parameter popup) are unchanged.
from core.parameter_types import split_name_and_unit
from ui_qt import icons, style, typography

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
#: the "-" of a committed null and the derived summaries of Inspector-only
#: kinds ("table · 3 points"), as opposed to a verbatim raw value.
VALUE_GHOST_ROLE = Qt.UserRole + 102
#: Item-data role carrying ``"error"``/``"warning"`` for an issue row; when
#: present the delegate paints a small filled-circle severity icon in the
#: row's left gutter, replacing the old bracketed ``[ERROR]``/``[WARN]``
#: text tag baked into the HTML. Shared by
#: :mod:`ui_qt.diagnostics_panel` and :mod:`ui_qt.issues_view` so both issue
#: surfaces read identically -- this lives on the base delegate, not a
#: page-specific subclass, precisely so the two never diverge.
SEVERITY_ROLE = Qt.UserRole + 103
#: Item-data role carrying a row's right-aligned call-to-action string
#: (e.g. a Diagnostics Outstanding row's "Go to ▸"), painted in
#: ``style.ACCENT``: every actionable row displays its own
#: action, always visible, never folded inline with the name (unlike
#: :data:`VALUE_ROLE`, a muted monospace value preview, this is normal-
#: weight coloured text and is never elided -- keep the string short).
#: Lives on the base delegate, not a page-specific subclass, so any future
#: right-aligned-action row reuses the same reserved-width machinery
#: :data:`VALUE_ROLE` already established for a row's right edge.
ACTION_ROLE = Qt.UserRole + 104
#: Item-data role carrying a row's reference-comparison bar variant --
#: ``"differs"`` (solid :data:`~ui_qt.style.REFERENCE`), ``"equal"`` (pale
#: :data:`~ui_qt.style.REFERENCE_BORDER`) or ``"ref_only"`` (hollow
#: :data:`~ui_qt.style.REFERENCE_SOFT` outline) -- painted by the delegate
#: as a 3px bar on the row's left edge, the source-control gutter idiom.
#: Absent (``None``) when no reference is docked or the reference has no
#: entry for this row (MAIN_ONLY). Painted directly by the delegate --
#: **not** via ``QListWidgetItem.setBackground``, whose ``Qt.BackgroundRole``
#: a stylesheet-styled ``::item`` silently ignores once any such rule exists
#: for the view (a real Qt/QSS gotcha; a plain data read back from the item
#: would look correct in an offscreen test while never actually painting).
#: Unlike the background washes this replaced, the bar paints *after* the
#: row background, so comparison state stays readable on a selected row.
REF_BAR_ROLE = Qt.UserRole + 105

_MIN_WIDTH = 40
#: The value preview never claims more than this share of the row, however
#: long the raw value is -- the name keeps priority, the value elides.
_VALUE_MAX_SHARE = 0.45
#: Gap between the (wrapped) name fragment and the value preview.
_VALUE_GAP = 12

#: The app's one painted severity mark: an 8px filled dot centred in a
#: 13px box. ``MARK_BOX`` is the box a caller sizes its own paint rect to;
#: ``MARK_DOT`` is the fixed dot diameter :func:`paint_severity_dot`
#: centres inside whatever box it is given.
MARK_BOX = typography.BODY
MARK_DOT = 8

#: Reference gutter bar: width, vertical inset from the row's edges, and
#: corner radius. Shared by :func:`paint_ref_bar`'s two callers (the
#: parameter list's :class:`ParameterRowDelegate` and the navigation tree's
#: ``_TreeItemDelegate``) so both rails read as one system.
REF_BAR_WIDTH = 3
REF_BAR_INSET = 4
REF_BAR_RADIUS = 1.5


def paint_ref_bar(painter: QPainter, rect: QRect, variant: str) -> None:
    """Paint a reference-comparison gutter bar flush against *rect*'s left
    edge: solid purple = differs/fillable, pale lilac = present in the
    reference and equal, hollow outline = reference-only ghost row.

    *rect* is whatever row rect the caller paints against (a list row's
    ``option.rect``, or the tree's full-width viewport rect) -- this
    function only reads its left/top/height, so callers control exactly
    where the bar's rail sits. Painted after the row background so it stays
    visible on a selected row."""
    bar = QRectF(
        rect.left(),
        rect.top() + REF_BAR_INSET,
        REF_BAR_WIDTH,
        rect.height() - 2 * REF_BAR_INSET,
    )
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    if variant == "ref_only":
        painter.setPen(QPen(QColor(style.REFERENCE_SOFT)))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            bar.adjusted(0.5, 0.5, -0.5, -0.5), REF_BAR_RADIUS, REF_BAR_RADIUS
        )
    else:
        painter.setPen(Qt.NoPen)
        fill = style.REFERENCE if variant == "differs" else style.REFERENCE_BORDER
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(bar, REF_BAR_RADIUS, REF_BAR_RADIUS)
    painter.restore()


def paint_severity_dot(painter: QPainter, box: QRect, color: str) -> None:
    """Paint one filled *color* dot, :data:`MARK_DOT` wide, centred in
    *box* -- the single painted-mark helper every red/amber circle in the
    app shares: this delegate's own left-gutter issue icon
    (:meth:`ParameterRowDelegate._paint_severity_icon`) and the navigation
    tree's after-label error dot (:mod:`ui_qt.tree_panel`)."""
    offset = (box.width() - MARK_DOT) / 2
    dot = QRectF(box).adjusted(offset, offset, -offset, -offset)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(dot)
    painter.restore()


def cap_midline_mark_top(text_rect: QRect, metrics: QFontMetrics, mark_size: int) -> int:
    """The y (top) for a *mark_size*-square mark -- typically a
    :func:`paint_severity_dot` *box* -- so it centres on the **cap
    midline** of text vertically centred within *text_rect* per *metrics*,
    rather than on *text_rect*'s own geometric centre.

    First the ordinary vertically-centred-text baseline (``text_rect.y() +
    (text_rect.height() + ascent - descent) // 2``, integer like Qt's own
    text-centring maths); then up half a cap height to the midline capital
    letters and digits optically centre on; then up half the mark to
    centre it there too. A mark placed on *text_rect*'s bare geometric
    centre instead sits on the wrong line, because a font's ascent/descent
    span reaches well past where capital-letter ink actually stops.

    The one derivation every mark that sits *beside* a known text rect
    should share -- used directly here by the navigation tree's after-label
    error dot (:mod:`ui_qt.tree_panel`); :mod:`ui_qt.icons`'s ``html_img``
    inline lift is the equivalent correction for a mark that is instead
    *embedded inside* a line of rich text, where no such rect is
    available."""
    baseline = text_rect.y() + (text_rect.height() + metrics.ascent() - metrics.descent()) // 2
    return round(baseline - metrics.capHeight() / 2 - mark_size / 2)


def value_preview(value: object, kind: ParameterKind) -> tuple[str, bool]:
    """Return ``(text, ghost)`` for a parameter row's value column.

    Simple committed values render **verbatim from the raw document** (JSON
    spelling for numbers and booleans, the bare string for text) -- never
    reformatted, rounded or re-spelled, per validator fidelity. Committed
    ``null`` renders as a ghosted "-" (the app's muted-emptiness language).
    Inspector-only kinds render a ghosted summary *derived*
    from the data (point/entry/value counts), never invented content.
    Elision to the available width is the delegate's job, not this one's:
    the full string is returned so tooltips can carry it.
    """
    if value is None:
        return "-", True
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


def _span(text: str, *, color: str, bold: bool = False) -> str:
    weight = typography.SEMIBOLD if bold else typography.REGULAR
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


def compose_issue_row_html(location: str, message: str, detail: str | None = None) -> str:
    """Compose an issue row's rich-text fragment: the bold location on the
    first line, the validator's verbatim message (muted, smaller) on the
    second -- or the message alone when there is no location to show.

    Splitting where (location) from what (message) is the core move here --
    a full-width run-on sentence per issue becomes a scannable header with its
    detail beneath. Severity used to be a bracketed ``[ERROR]``/``[WARN]``
    text tag on the first line; a delegate-painted icon (see
    :data:`SEVERITY_ROLE`) replaced it, reading clearly at a glance without
    competing with the location text for space --
    callers set that role alongside this HTML, they no longer pass severity
    in here. Shared by the Diagnostics page's Issues section and the
    Inspector's Issues tab so the two issue surfaces read as one system; the
    tab passes an empty *location* (it is already scoped to one parameter),
    which drops the row to a single message line rather than an empty first
    line. *location* is expected already section-relative (the owning
    section is the group header/rail entry above the row), and its trailing
    unit is muted like every other parameter label.

    *detail* is an optional short fact (e.g. :func:`core.validation.
    input_fact`'s offending value) appended after *message* with the app's
    " · " separator, inside the same span -- same muted style, same line --
    never altering *message* itself. ``None``/empty omits it entirely."""
    full_message = f"{message} · {detail}" if detail else message
    if not location:
        # The message is the whole row here (a document-level diagnostic, or
        # the Issues tab, already scoped to one parameter). Muted META is the
        # right weight for a *second* line under a bold location; as the only
        # line it made the page's actual content read as a footnote, so it
        # takes the body rung and the body colour instead.
        return _span(full_message, color=style.DEFAULT_TEXT)
    message_html = (
        f'<span style="color:{style.MUTED}; {typography.size_qss(typography.META)}">'
        f"{_html.escape(full_message)}</span>"
    )
    name, unit = split_name_and_unit(location)
    head = _span(name, color=style.DEFAULT_TEXT, bold=True)
    if unit:
        head += _span(f" [{unit}]", color=style.MUTED)
    return head + "<br>" + message_html


def build_parameter_row_html(label: str, *, severity: str | None = None, is_empty: bool = False) -> str:
    """Compose a parameter-list row's rich-text fragment: bold name, a muted
    non-bold unit, and -- for a parameter with a *page-visible* issue -- a
    trailing dot mark (:data:`icons.DOT`) after the label text, coloured by
    *severity*.

    ``severity`` is ``"error"``/``"warning"``/``None`` and means *page-
    visible*, not validator-verbatim: the caller passes the worst severity
    among this parameter's issues that survived absorption
    (``core.completion.partition_issues``'s ``visible``), not
    ``parameter.has_errors``. The card's own inline badge and the Issues
    tab still mirror the validator verbatim -- only this row marker's
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
    name_color = style.MUTED if is_empty else style.DEFAULT_TEXT
    fragment = _span(name, color=name_color, bold=True)
    if unit:
        fragment += _span(f" [{unit}]", color=style.MUTED)
    if severity:
        color = style.ERROR if severity == "error" else style.WARNING
        fragment += "  " + icons.html_img(icons.DOT, color=color, size=MARK_BOX)
    return fragment


def build_ghost_row_html(label: str) -> str:
    """Compose a REF_ONLY ghost row's rich-text fragment: name and unit in
    ghosted italic text -- quiet, clearly not a real row. The reference-only
    state itself is carried by the hollow gutter bar
    (:data:`REF_BAR_ROLE`), not a text tag."""
    name, unit = split_name_and_unit(label)
    fragment = _span(name, color=style.GHOST_TEXT, bold=True)
    if unit:
        fragment += _span(f" [{unit}]", color=style.GHOST_TEXT)
    return f"<i>{fragment}</i>"


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

    #: Box the delegate-painted severity icon (:data:`SEVERITY_ROLE`) occupies
    #: (:data:`MARK_BOX`), plus the gap before the row's own text starts.
    _ICON_SIZE = MARK_BOX
    _ICON_GUTTER = _ICON_SIZE + 8

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
        """The value preview's font: the app's monospace face, at the same
        rung as the row -- digits align across rows and a long mantissa
        reads as data rather than prose. Unlike the old system fixed-pitch
        face (Courier New), Cascadia Mono's cap height at 13px (9.0) matches
        Segoe UI's (9.1), so no "one step smaller" fudge is needed."""
        return typography.mono(typography.BODY)

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

    def _icon_reserved(self, index) -> int:
        """Row width the severity icon claims (including its gap), 0 for a
        row with no :data:`SEVERITY_ROLE`."""
        return self._ICON_GUTTER if index.data(SEVERITY_ROLE) else 0

    def _action_font(self, option: QStyleOptionViewItem) -> QFont:
        """Normal weight, matching the row's own font -- ``style.ACCENT``
        alone (not bold) carries the emphasis, same as the old inline
        action hint's own styling (:func:`compose_row_html`)."""
        return QFont(option.font)

    def _action_reserved(self, option: QStyleOptionViewItem, index) -> int:
        """Row width the right-aligned call-to-action (:data:`ACTION_ROLE`)
        claims (including its gap), 0 for a row with none. Never elided --
        action strings are short by convention ("Go to ▸", "+ Add section",
        "Choose…"), so unlike :data:`VALUE_ROLE` this reserves its full
        natural width rather than capping/eliding against the row."""
        text = index.data(ACTION_ROLE)
        if not text:
            return 0
        metrics = QFontMetrics(self._action_font(option))
        return metrics.horizontalAdvance(text) + _VALUE_GAP

    def sizeHint(self, option, index):
        width = self._available_width(option)
        reserved = (
            self._value_reserved(option, index, width)
            + self._icon_reserved(index)
            + self._action_reserved(option, index)
        )
        doc = self._build_document(option, index, width - 2 * self._h_pad - reserved)
        if doc is None:
            return super().sizeHint(option, index)
        return QSize(int(width), int(doc.size().height()) + 2 * self._v_pad)

    def paint(self, painter, option, index) -> None:
        row_width = option.rect.width() if option.rect.width() > 0 else self._available_width(option)
        icon_reserved = self._icon_reserved(index)
        action_reserved = self._action_reserved(option, index)
        value_reserved = self._value_reserved(option, index, row_width)
        text_width = row_width - 2 * self._h_pad - icon_reserved - action_reserved - value_reserved
        doc = self._build_document(option, index, text_width)
        if doc is None:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style_obj = widget.style() if widget is not None else QApplication.style()
        style_obj.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)

        bar = index.data(REF_BAR_ROLE)
        if bar:
            self._paint_ref_bar(painter, option, bar)
        if icon_reserved:
            self._paint_severity_icon(painter, option, index)

        painter.save()
        painter.translate(
            option.rect.left() + self._h_pad + icon_reserved, option.rect.top() + self._v_pad
        )
        doc.drawContents(painter)
        painter.restore()

        if action_reserved:
            self._paint_action(painter, option, index, action_reserved)
        if value_reserved:
            self._paint_value(painter, option, index, value_reserved)

    def _paint_ref_bar(self, painter, option, variant: str) -> None:
        """Paint the row's reference-comparison bar (:data:`REF_BAR_ROLE`)
        on its left edge, left of the ``_h_pad`` region so it never collides
        with the severity dot gutter -- geometry and colours live in the
        shared :func:`paint_ref_bar` (also used by the navigation tree's own
        rail, :mod:`ui_qt.tree_panel`)."""
        paint_ref_bar(painter, option.rect, variant)

    def _name_baseline(self, option: QStyleOptionViewItem) -> float:
        """Y of the parameter name's first-line baseline (row top + ``_v_pad``
        + the row font's ascent) -- the anchor :meth:`_paint_value` and
        :meth:`_paint_action` align their own, differently-sized text to, so
        neither floats above the name like a superscript."""
        return option.rect.top() + self._v_pad + QFontMetrics(option.font).ascent()

    def _paint_action(self, painter, option, index, reserved: int) -> None:
        """Right-aligned call-to-action text in accent colour, baseline-
        aligned with the parameter name's first line -- always fully
        visible, never folded inline with the name."""
        painter.save()
        font = self._action_font(option)
        painter.setFont(font)
        painter.setPen(QColor(style.ACCENT))
        text = index.data(ACTION_ROLE)
        x = option.rect.right() - self._h_pad - QFontMetrics(font).horizontalAdvance(text)
        painter.drawText(QPointF(x, self._name_baseline(option)), text)
        painter.restore()

    def _paint_severity_icon(self, painter, option: QStyleOptionViewItem, index) -> None:
        """Paint the shared severity dot (:func:`paint_severity_dot`) in the
        row's left gutter: red = error, amber = warning, no inner glyph --
        a plain dot reads better at row size than the
        earlier icon-in-circle (a bracketed ``[ERROR]``/``[WARN]`` text tag
        before that). Part of the app's unified dot vocabulary alongside a
        task row's own ring/half-filled marks (:mod:`ui_qt.diagnostics_panel`);
        see ``style.severity_tooltip``/``style.task_kind_tooltip`` for the
        matching, drift-safe tooltip text."""
        severity = index.data(SEVERITY_ROLE)
        is_error = severity == "error"
        box = QRect(
            option.rect.left() + self._h_pad,
            option.rect.top() + self._v_pad,
            self._ICON_SIZE,
            self._ICON_SIZE,
        )
        paint_severity_dot(painter, box, style.ERROR if is_error else style.WARNING)

    def _paint_value(self, painter, option, index, reserved: int) -> None:
        """Right-aligned value preview, elided with "…" to the reserved
        width and baseline-aligned with the parameter name's first line --
        elision is visual only; the full string travels on the item's
        tooltip."""
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
        painter.setPen(QColor(style.GHOST_TEXT if ghost else style.MUTED))
        x = option.rect.right() - self._h_pad - metrics.horizontalAdvance(elided)
        painter.drawText(QPointF(x, self._name_baseline(option)), elided)
        painter.restore()
