"""Source page (multi-file track, ``PLAN-multi-file.md`` M5, decision 13):
the document's formatted raw JSON, live against the session.

With no reference docked the page shows one full-width pane of the main
file -- monospace, collapsible section headers, "n parameters" sizes, and a
quiet toolbar hint that docking a reference turns the page into a split
comparison. The aligned two-pane mode builds on this same row model in a
later step.

The page never edits: it contains no input widget, ever (coexistence rule
14). All content is painted by :class:`SourceView`, a custom scroll area
over :func:`core.source_rows.build_rows` -- deliberately not entangled with
``BpxTreeModel`` (the plan's risk note): the Source page owns its own
row/fold state.
"""

from __future__ import annotations

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

from core.source_rows import RowKind, SourceRow, build_rows, format_value
from ui_qt import style

#: One indent step, in pixels, per nesting depth.
_INDENT_PX = 18
#: Left margin before depth-0 text; also the caret column's width.
_LEFT_MARGIN = 10
#: Vertical padding added to the font's line height.
_LINE_PADDING = 6

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
class _Line:
    """One painted line of the pane."""

    segments: tuple[_Segment, ...]
    depth: int
    #: Clicking a line that carries a caret toggles this fold path (a
    #: section, or a closable dict/list parameter).
    toggle_path: tuple[str, ...] | None = None
    caret: str | None = None

    @property
    def text(self) -> str:
        return "".join(segment.text for segment in self.segments)


def _param_counts(rows: list[SourceRow]) -> dict[tuple[str, ...], int]:
    """Per-section count of parameter rows anywhere beneath it."""
    counts: dict[tuple[str, ...], int] = {
        row.path: 0 for row in rows if row.kind is RowKind.SECTION
    }
    for row in rows:
        if row.kind is not RowKind.PARAM:
            continue
        for depth in range(1, len(row.path)):
            prefix = row.path[:depth]
            if prefix in counts:
                counts[prefix] += 1
    return counts


def _value_lines(key: str, value: object, depth: int) -> list[_Line]:
    """A dict/list value rendered whole: key line, indented body, closer."""
    dumped = json.dumps(value, indent=2, ensure_ascii=False).splitlines()
    opener, body, closer = dumped[0], dumped[1:-1], dumped[-1]
    lines = [
        _Line(
            segments=(_Segment(f'"{key}": {opener}'),),
            depth=depth,
            toggle_path=None,  # caller fills in the toggle/caret
        )
    ]
    for raw_line in body:
        # json.dumps indents by 2 spaces per level; re-map that onto the
        # pane's own depth steps so the body sits under its key line.
        stripped = raw_line.lstrip(" ")
        extra = (len(raw_line) - len(stripped)) // 2
        lines.append(_Line(segments=(_Segment(stripped),), depth=depth + extra))
    lines.append(_Line(segments=(_Segment(closer),), depth=depth))
    return lines


def _build_lines(
    rows: list[SourceRow], closed: set[tuple[str, ...]]
) -> list[_Line]:
    counts = _param_counts(rows)
    lines: list[_Line] = []
    for row in rows:
        # Anything under a closed section stays unrendered.
        if any(row.path[:n] in closed for n in range(1, len(row.path))):
            continue
        if row.kind is RowKind.SECTION:
            is_closed = row.path in closed
            n = counts.get(row.path, 0)
            noun = "parameter" if n == 1 else "parameters"
            lines.append(
                _Line(
                    segments=(
                        _Segment(row.key, bold=True),
                        _Segment(f"  ·  {n} {noun}", color=style.MUTED),
                    ),
                    depth=row.depth,
                    toggle_path=row.path,
                    caret=_CARET_CLOSED if is_closed else _CARET_OPEN,
                )
            )
        elif row.closable:
            if row.path in closed:
                lines.append(
                    _Line(
                        segments=(
                            _Segment(f'"{row.key}": '),
                            _Segment(_CLOSED_SUMMARY, color=style.MUTED, italic=True),
                        ),
                        depth=row.depth,
                        toggle_path=row.path,
                        caret=_CARET_CLOSED,
                    )
                )
            else:
                whole = _value_lines(row.key, row.main_value, row.depth)
                lines.append(
                    _Line(
                        segments=whole[0].segments,
                        depth=whole[0].depth,
                        toggle_path=row.path,
                        caret=_CARET_OPEN,
                    )
                )
                lines.extend(whole[1:])
        else:
            lines.append(
                _Line(
                    segments=(
                        _Segment(f'"{row.key}": {format_value(row.main_value)}'),
                    ),
                    depth=row.depth,
                )
            )
    return lines


class SourceView(QAbstractScrollArea):
    """Custom-painted, read-only pane of formatted raw JSON.

    Owns its own fold state (``_closed``: section paths and closed
    dict/list parameters), preserved across refreshes so a live re-render
    after an edit or undo never loses where the user folded.
    """

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[SourceRow] = []
        self._closed: set[tuple[str, ...]] = set()
        self._lines: list[_Line] = []
        self._font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.setFocusPolicy(Qt.NoFocus)

    # -- content ---------------------------------------------------------

    def set_rows(self, rows: list[SourceRow]) -> None:
        """Replace the rendered rows, pruning fold state for paths that no
        longer exist (a removed section must not haunt the closed set)."""
        self._rows = rows
        foldable = {
            row.path
            for row in rows
            if row.kind is RowKind.SECTION or row.closable
        }
        self._closed &= foldable
        self._rebuild()

    def toggle_fold(self, path: tuple[str, ...]) -> None:
        """Fold/unfold the section or closable value at *path*."""
        if path in self._closed:
            self._closed.discard(path)
        else:
            self._closed.add(path)
        self._rebuild()

    def line_texts(self) -> list[str]:
        """Plain text of every currently rendered line, top to bottom --
        the test-facing read of what the pane shows."""
        return [line.text for line in self._lines]

    # -- geometry --------------------------------------------------------

    def _line_height(self) -> int:
        return self.fontMetrics().height() + _LINE_PADDING

    def _line_x(self, line: _Line) -> int:
        return _LEFT_MARGIN + line.depth * _INDENT_PX + 14

    def _rebuild(self) -> None:
        self._lines = _build_lines(self._rows, self._closed)
        self._update_scrollbars()
        self.viewport().update()

    def _update_scrollbars(self) -> None:
        line_height = self._line_height()
        metrics = self.fontMetrics()
        content_height = len(self._lines) * line_height
        content_width = max(
            (self._line_x(line) + metrics.horizontalAdvance(line.text) for line in self._lines),
            default=0,
        )
        self.verticalScrollBar().setRange(
            0, max(0, content_height - self.viewport().height())
        )
        self.verticalScrollBar().setSingleStep(line_height)
        self.verticalScrollBar().setPageStep(self.viewport().height())
        self.horizontalScrollBar().setRange(
            0, max(0, content_width + 12 - self.viewport().width())
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
        first = max(0, v_offset // line_height)
        last = min(
            len(self._lines),
            (v_offset + self.viewport().height()) // line_height + 2,
        )
        ascent_y = (line_height + self.fontMetrics().ascent()) // 2 - 2
        for index in range(first, last):
            line = self._lines[index]
            y = index * line_height - v_offset + ascent_y
            if line.caret is not None:
                font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
                painter.setFont(font)
                painter.setPen(QColor(style.MUTED))
                caret_x = _LEFT_MARGIN + line.depth * _INDENT_PX - h_offset
                painter.drawText(caret_x, y, line.caret)
            x = self._line_x(line) - h_offset
            for segment in line.segments:
                font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
                font.setBold(segment.bold)
                font.setItalic(segment.italic)
                painter.setFont(font)
                painter.setPen(QColor(segment.color))
                painter.drawText(x, y, segment.text)
                x += painter.fontMetrics().horizontalAdvance(segment.text)
        painter.end()

    # -- interaction -----------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        index = (event.position().toPoint().y() + self.verticalScrollBar().value()) // self._line_height()
        if 0 <= index < len(self._lines):
            line = self._lines[int(index)]
            if line.toggle_path is not None:
                self.toggle_fold(line.toggle_path)
                return
        super().mousePressEvent(event)


class SourcePage(QWidget):
    """The Source rail page: toolbar strip + the raw-JSON view."""

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(self._view, 1)

    def refresh(self, main_raw: dict | None, reference=None) -> None:
        """Re-render from the current document (and, later, reference).

        Called from ``MainWindow._apply_comparison`` -- the same fan-out
        every comparison-state change already goes through -- so edits,
        undo/redo, open/new and reference dock/undock all land here. The
        *reference* snapshot only drives the toolbar hint until the aligned
        two-pane mode (next step) renders its raw dict.
        """
        self._hint.setVisible(main_raw is not None and reference is None)
        self._view.set_rows(build_rows(main_raw) if main_raw is not None else [])
