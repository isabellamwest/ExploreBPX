"""Source page (multi-file track, ``PLAN-multi-file.md`` M5, decision 13):
the document's formatted raw JSON, live against the session.

With no reference docked the page shows one full-width pane of the main
file -- monospace, collapsible section headers, "n parameters" sizes, and a
quiet toolbar hint that docking a reference turns the page into a split
comparison. With a reference docked the same rows render as two panes
aligned line by line: a centre gutter column separates them, a flat grey
block marks a key one side lacks, reference-only rows read in the
reference purple, and fillable keys grey out with no value. Section and
table folding is shared -- one caret folds both panes together.

The page never edits: it contains no input widget, ever (coexistence rule
14). All content is painted by :class:`SourceView`, a custom scroll area
over :func:`core.source_rows.build_rows` -- deliberately not entangled with
``BpxTreeModel`` (the plan's risk note): the Source page owns its own
row/fold state.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QPainter
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.compare import RowState
from core.source_rows import RowKind, SourceRow, build_rows, format_value
from ui_qt import style

#: One indent step, in pixels, per nesting depth.
_INDENT_PX = 18
#: Left margin before depth-0 text; also the caret column's width.
_LEFT_MARGIN = 10
#: Vertical padding added to the font's line height.
_LINE_PADDING = 6
#: The centre column between the two panes; the ← copy affordances land
#: here in a later step, the width is reserved now so the layout is stable.
_GUTTER_PX = 40

_CARET_OPEN = "▾"
_CARET_CLOSED = "▸"

#: The one-line stand-in for a closed dict/list value (decision 15).
_CLOSED_SUMMARY = "table"


@dataclass(frozen=True)
class _Segment:
    """One run of same-styled text within a line."""

    text: str
    color: str = style.DEFAULT_TEXT
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class _PaneLine:
    """One pane's share of an aligned line.

    ``gap`` renders as the flat grey block: the key exists on the other
    side only, and this side shows structure-preserving absence rather
    than collapsing the alignment.
    """

    segments: tuple[_Segment, ...] = ()
    depth: int = 0
    caret: str | None = None
    gap: bool = False

    @property
    def text(self) -> str:
        return "".join(segment.text for segment in self.segments)


@dataclass(frozen=True)
class _Line:
    """One painted line: the main pane always, the reference pane only in
    two-pane mode (``None`` while no reference is docked)."""

    main: _PaneLine
    ref: _PaneLine | None = None
    #: Clicking a line that carries a caret toggles this fold path (a
    #: section, or a closable dict/list parameter); the fold state is one
    #: shared set, so both panes fold together.
    toggle_path: tuple[str, ...] | None = None


def _gap(depth: int) -> _PaneLine:
    return _PaneLine(depth=depth, gap=True)


def _param_counts(
    rows: list[SourceRow], present
) -> dict[tuple[str, ...], int]:
    """Per-section count of parameter rows beneath it, counting only rows
    the *present* predicate admits -- so each pane's header counts its own
    side's parameters."""
    counts: dict[tuple[str, ...], int] = {
        row.path: 0 for row in rows if row.kind is RowKind.SECTION
    }
    for row in rows:
        if row.kind is not RowKind.PARAM or not present(row):
            continue
        for depth in range(1, len(row.path)):
            prefix = row.path[:depth]
            if prefix in counts:
                counts[prefix] += 1
    return counts


def _section_pane(
    row: SourceRow, key_color: str, count: int, is_closed: bool
) -> _PaneLine:
    noun = "parameter" if count == 1 else "parameters"
    return _PaneLine(
        segments=(
            _Segment(row.key, color=key_color, bold=True),
            _Segment(f"  ·  {count} {noun}", color=style.MUTED),
        ),
        depth=row.depth,
        caret=_CARET_CLOSED if is_closed else _CARET_OPEN,
    )


def _open_value_panes(
    key: str, value: object, depth: int, color: str
) -> list[_PaneLine]:
    """A dict/list value rendered whole: key line, indented body, closer."""
    dumped = json.dumps(value, indent=2, ensure_ascii=False).splitlines()
    opener, body, closer = dumped[0], dumped[1:-1], dumped[-1]
    panes = [
        _PaneLine(
            segments=(_Segment(f'"{key}": {opener}', color=color),),
            depth=depth,
            caret=_CARET_OPEN,
        )
    ]
    for raw_line in body:
        # json.dumps indents by 2 spaces per level; re-map that onto the
        # pane's own depth steps so the body sits under its key line.
        stripped = raw_line.lstrip(" ")
        extra = (len(raw_line) - len(stripped)) // 2
        panes.append(
            _PaneLine(
                segments=(_Segment(stripped, color=color),), depth=depth + extra
            )
        )
    panes.append(_PaneLine(segments=(_Segment(closer, color=color),), depth=depth))
    return panes


def _param_side_panes(
    row: SourceRow,
    value: object,
    present: bool,
    color: str,
    fillable: bool,
    is_closed: bool,
) -> list[_PaneLine]:
    """One side's lines for a PARAM row; empty when the side lacks the key
    (the caller pads with gap blocks to keep the panes aligned)."""
    if not present:
        return []
    if fillable:
        # The signed frames' fillable rendering: grey key, no value -- the
        # slot is there, nothing meaningful fills it yet.
        return [
            _PaneLine(
                segments=(_Segment(f'"{row.key}":', color=style.GHOST_TEXT),),
                depth=row.depth,
            )
        ]
    if isinstance(value, (dict, list)):
        if is_closed:
            return [
                _PaneLine(
                    segments=(
                        _Segment(f'"{row.key}": ', color=color),
                        _Segment(_CLOSED_SUMMARY, color=style.MUTED, italic=True),
                    ),
                    depth=row.depth,
                    caret=_CARET_CLOSED,
                )
            ]
        return _open_value_panes(row.key, value, row.depth, color)
    return [
        _PaneLine(
            segments=(
                _Segment(f'"{row.key}": {format_value(value)}', color=color),
            ),
            depth=row.depth,
        )
    ]


def _align_panes(
    main_panes: list[_PaneLine], ref_panes: list[_PaneLine], depth: int
) -> list[tuple[_PaneLine, _PaneLine]]:
    """Pair one parameter's two sides line by line: identical JSON lines
    pair up, unmatched lines face a gap block -- so a longer table pads
    beside its extra entries, inside the table, never at its tail."""
    gap = _gap(depth)
    if not main_panes:
        return [(gap, pane) for pane in ref_panes]
    if not ref_panes:
        return [(pane, gap) for pane in main_panes]
    matcher = difflib.SequenceMatcher(
        None,
        [pane.text for pane in main_panes],
        [pane.text for pane in ref_panes],
        autojunk=False,
    )
    pairs: list[tuple[_PaneLine, _PaneLine]] = []
    for tag, m1, m2, r1, r2 in matcher.get_opcodes():
        if tag in ("equal", "replace"):
            for offset in range(max(m2 - m1, r2 - r1)):
                pairs.append(
                    (
                        main_panes[m1 + offset] if m1 + offset < m2 else gap,
                        ref_panes[r1 + offset] if r1 + offset < r2 else gap,
                    )
                )
        elif tag == "delete":
            pairs.extend((pane, gap) for pane in main_panes[m1:m2])
        else:  # insert
            pairs.extend((gap, pane) for pane in ref_panes[r1:r2])
    return pairs


def _build_lines(
    rows: list[SourceRow], closed: set[tuple[str, ...]], two_pane: bool
) -> list[_Line]:
    counts_main = _param_counts(rows, lambda row: row.in_main)
    counts_ref = (
        _param_counts(rows, lambda row: row.in_reference) if two_pane else {}
    )
    lines: list[_Line] = []
    for row in rows:
        # Anything under a closed section stays unrendered, on both sides.
        if any(row.path[:n] in closed for n in range(1, len(row.path))):
            continue
        is_closed = row.path in closed
        if row.kind is RowKind.SECTION:
            main = (
                _section_pane(
                    row, style.DEFAULT_TEXT, counts_main.get(row.path, 0), is_closed
                )
                if row.in_main
                else _gap(row.depth)
            )
            ref = None
            if two_pane:
                key_color = (
                    style.REFERENCE if not row.in_main else style.DEFAULT_TEXT
                )
                ref = (
                    _section_pane(
                        row, key_color, counts_ref.get(row.path, 0), is_closed
                    )
                    if row.in_reference
                    else _gap(row.depth)
                )
            lines.append(_Line(main=main, ref=ref, toggle_path=row.path))
        else:
            main_panes = _param_side_panes(
                row,
                row.main_value,
                row.in_main,
                style.DEFAULT_TEXT,
                two_pane and row.state is RowState.FILLABLE,
                is_closed,
            )
            if two_pane:
                value_color = (
                    style.REFERENCE
                    if row.state is RowState.REF_ONLY
                    else style.DEFAULT_TEXT
                )
                ref_panes = _param_side_panes(
                    row, row.ref_value, row.in_reference, value_color, False, is_closed
                )
                for index, (main, ref) in enumerate(
                    _align_panes(main_panes, ref_panes, row.depth)
                ):
                    lines.append(
                        _Line(
                            main=main,
                            ref=ref,
                            toggle_path=row.path
                            if index == 0 and row.closable
                            else None,
                        )
                    )
            else:
                for index, main in enumerate(main_panes):
                    lines.append(
                        _Line(
                            main=main,
                            toggle_path=row.path
                            if index == 0 and row.closable
                            else None,
                        )
                    )
    return lines


class SourceView(QAbstractScrollArea):
    """Custom-painted, read-only pane(s) of formatted raw JSON.

    Owns its own fold state (``_closed``: section paths and closed
    dict/list parameters), preserved across refreshes so a live re-render
    after an edit or undo never loses where the user folded. In two-pane
    mode the same fold set drives both panes.
    """

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[SourceRow] = []
        self._two_pane = False
        self._closed: set[tuple[str, ...]] = set()
        self._lines: list[_Line] = []
        self._font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.setFocusPolicy(Qt.NoFocus)

    # -- content ---------------------------------------------------------

    def set_rows(self, rows: list[SourceRow], two_pane: bool = False) -> None:
        """Replace the rendered rows, pruning fold state for paths that no
        longer exist (a removed section must not haunt the closed set)."""
        self._rows = rows
        self._two_pane = two_pane
        foldable = {
            row.path
            for row in rows
            if row.kind is RowKind.SECTION or row.closable
        }
        self._closed &= foldable
        self._rebuild()

    def toggle_fold(self, path: tuple[str, ...]) -> None:
        """Fold/unfold the section or closable value at *path* -- in both
        panes at once (shared fold state)."""
        if path in self._closed:
            self._closed.discard(path)
        else:
            self._closed.add(path)
        self._rebuild()

    def line_texts(self) -> list[str]:
        """Plain text of every currently rendered main-pane line, top to
        bottom -- the test-facing read of what the pane shows. Gap blocks
        read as empty strings, keeping indices aligned across panes."""
        return [line.main.text for line in self._lines]

    def ref_line_texts(self) -> list[str]:
        """Reference-pane counterpart of :meth:`line_texts`; empty while
        no reference is docked."""
        if not self._two_pane:
            return []
        return [line.ref.text if line.ref is not None else "" for line in self._lines]

    # -- geometry --------------------------------------------------------

    def _line_height(self) -> int:
        return self.fontMetrics().height() + _LINE_PADDING

    def _pane_width(self) -> int:
        if not self._two_pane:
            return self.viewport().width()
        return max(0, (self.viewport().width() - _GUTTER_PX) // 2)

    def _pane_x(self, pane: _PaneLine) -> int:
        return _LEFT_MARGIN + pane.depth * _INDENT_PX + 14

    def _rebuild(self) -> None:
        self._lines = _build_lines(self._rows, self._closed, self._two_pane)
        self._update_scrollbars()
        self.viewport().update()

    def _update_scrollbars(self) -> None:
        line_height = self._line_height()
        metrics = self.fontMetrics()
        content_height = len(self._lines) * line_height
        panes = [line.main for line in self._lines]
        panes += [line.ref for line in self._lines if line.ref is not None]
        content_width = max(
            (
                self._pane_x(pane) + metrics.horizontalAdvance(pane.text)
                for pane in panes
            ),
            default=0,
        )
        self.verticalScrollBar().setRange(
            0, max(0, content_height - self.viewport().height())
        )
        self.verticalScrollBar().setSingleStep(line_height)
        self.verticalScrollBar().setPageStep(self.viewport().height())
        self.horizontalScrollBar().setRange(
            0, max(0, content_width + 12 - self._pane_width())
        )
        self.horizontalScrollBar().setSingleStep(12)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._update_scrollbars()

    # -- painting --------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor("#ffffff"))
        line_height = self._line_height()
        v_offset = self.verticalScrollBar().value()
        h_offset = self.horizontalScrollBar().value()
        pane_width = self._pane_width()
        first = max(0, v_offset // line_height)
        last = min(
            len(self._lines),
            (v_offset + self.viewport().height()) // line_height + 2,
        )
        ascent = (line_height + self.fontMetrics().ascent()) // 2 - 2
        for index in range(first, last):
            line = self._lines[index]
            top = index * line_height - v_offset
            self._paint_pane(
                painter, line.main, 0, pane_width, top, top + ascent, h_offset,
                line_height,
            )
            if line.ref is not None:
                self._paint_pane(
                    painter,
                    line.ref,
                    pane_width + _GUTTER_PX,
                    pane_width,
                    top,
                    top + ascent,
                    h_offset,
                    line_height,
                )
        if self._two_pane:
            painter.setPen(QColor(style.NEUTRAL_TINT))
            painter.drawLine(pane_width, 0, pane_width, self.viewport().height())
            gutter_right = pane_width + _GUTTER_PX - 1
            painter.drawLine(gutter_right, 0, gutter_right, self.viewport().height())
        painter.end()

    def _paint_pane(
        self,
        painter: QPainter,
        pane: _PaneLine,
        x0: int,
        width: int,
        top: int,
        baseline: int,
        h_offset: int,
        line_height: int,
    ) -> None:
        if pane.gap:
            painter.fillRect(x0, top, width, line_height, QColor(style.NEUTRAL_TINT))
            return
        painter.save()
        painter.setClipRect(x0, top, width, line_height)
        if pane.caret is not None:
            font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            painter.setFont(font)
            painter.setPen(QColor(style.MUTED))
            caret_x = x0 + _LEFT_MARGIN + pane.depth * _INDENT_PX - h_offset
            painter.drawText(caret_x, baseline, pane.caret)
        x = x0 + self._pane_x(pane) - h_offset
        for segment in pane.segments:
            font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            font.setBold(segment.bold)
            font.setItalic(segment.italic)
            painter.setFont(font)
            painter.setPen(QColor(segment.color))
            painter.drawText(x, baseline, segment.text)
            x += painter.fontMetrics().horizontalAdvance(segment.text)
        painter.restore()

    # -- interaction -----------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        index = (event.position().toPoint().y() + self.verticalScrollBar().value()) // self._line_height()
        if 0 <= index < len(self._lines):
            line = self._lines[int(index)]
            if line.toggle_path is not None:
                self.toggle_fold(line.toggle_path)
                return
        super().mousePressEvent(event)


def _pane_header_text(role: str, filename: str, model: str | None) -> str:
    parts = [part for part in (role, filename, model) if part]
    return "  ·  ".join(parts)


class SourcePage(QWidget):
    """The Source rail page: toolbar strip + pane headers + the raw-JSON
    view (one pane, or two aligned panes with a reference docked)."""

    def __init__(self) -> None:
        super().__init__()
        self._view = SourceView()

        self._hint = QLabel("◇ Open a reference to compare…")
        self._hint.setStyleSheet(f"color: {style.MUTED};")

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 6, 10, 6)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self._hint)

        self._main_head = QLabel()
        self._main_head.setStyleSheet(
            f"color: {style.MUTED}; font-size: 11px; font-weight: 600;"
        )
        self._ref_head = QLabel()
        self._ref_head.setStyleSheet(
            f"color: {style.REFERENCE}; font-size: 11px; font-weight: 600;"
        )
        self._pane_head = QWidget()
        head_layout = QHBoxLayout(self._pane_head)
        head_layout.setContentsMargins(10, 2, 10, 2)
        head_layout.addWidget(self._main_head, 1)
        gutter_spacer = QWidget()
        gutter_spacer.setFixedWidth(_GUTTER_PX)
        head_layout.addWidget(gutter_spacer)
        head_layout.addWidget(self._ref_head, 1)
        self._pane_head.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(self._pane_head)
        layout.addWidget(self._view, 1)

    def refresh(
        self,
        main_raw: dict | None,
        reference=None,
        main_name: str = "",
        main_model: str | None = None,
    ) -> None:
        """Re-render from the current document and reference snapshot.

        Called from ``MainWindow._apply_comparison`` -- the same fan-out
        every comparison-state change already goes through -- so edits,
        undo/redo, open/new and reference dock/undock all land here. With
        a reference docked the page renders the aligned two-pane
        comparison; *main_name*/*main_model* label the main pane's header.
        """
        two_pane = main_raw is not None and reference is not None
        self._hint.setVisible(main_raw is not None and reference is None)
        self._pane_head.setVisible(two_pane)
        if two_pane:
            self._main_head.setText(
                _pane_header_text("Main", main_name, main_model)
            )
            self._ref_head.setText(
                "◇ " + _pane_header_text("Reference", reference.filename, reference.model)
            )
            rows = build_rows(main_raw, reference.raw)
        else:
            rows = build_rows(main_raw) if main_raw is not None else []
        self._view.set_rows(rows, two_pane=two_pane)
