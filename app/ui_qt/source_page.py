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
import re
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
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
_PULL_GLYPH = "←"
#: The ← chip's box inside the gutter column (the frames' 26×20 rounded
#: rect, centred).
_PULL_W = 26
_PULL_H = 20

#: The one-line stand-in for a closed dict/list value (decision 15).
_CLOSED_SUMMARY = "table"


@dataclass(frozen=True)
class _Segment:
    """One run of same-styled text within a line."""

    text: str
    color: str = style.DEFAULT_TEXT
    bold: bool = False
    italic: bool = False
    #: Painted over the ``style.DIFF_TINT`` wash: the value-only highlight
    #: chip of the signed frames. Only values (or the ⋯/"table" stand-ins)
    #: ever chip -- keys, structure and whole rows never do.
    chip: bool = False


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
    #: The ← gutter pull (two-pane only): set on the key line of a
    #: differs/fillable/ref-only parameter and on a ref-only section
    #: header -- the frames' rule: absent entirely on equal and main-only
    #: rows, and on shared section headers.
    pull_path: tuple[str, ...] | None = None
    pull_section: bool = False


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
    row: SourceRow,
    key_color: str,
    count: int,
    is_closed: bool,
    diff_dots: bool = False,
) -> _PaneLine:
    noun = "parameter" if count == 1 else "parameters"
    segments = [
        _Segment(row.key, color=key_color, bold=True),
        _Segment(f"  ·  {count} {noun}", color=style.MUTED),
    ]
    if diff_dots:
        # A collapsed section signals with a chipped ⋯ when anything inside
        # differs, is fillable or is ref-only (the signed frames' call: no
        # text counts, the chip carries the whole signal).
        segments += [_Segment("  "), _Segment("⋯", color=style.MUTED, chip=True)]
    return _PaneLine(
        segments=tuple(segments),
        depth=row.depth,
        caret=_CARET_CLOSED if is_closed else _CARET_OPEN,
    )


def _token_diff_segments(value: str, other: str, color: str) -> tuple[_Segment, ...]:
    """A differing string value rendered with only its changed parts
    chipped: whitespace-delimited tokens are diffed against the other
    side, so ``"8.3e-4 * exp(-4300 / T)"`` chips ``8.3e-4`` alone when the
    tail is shared (the signed frames' function-segment chips)."""
    dumped = format_value(value)[1:-1]
    other_dumped = format_value(other)[1:-1]
    tokens = re.split(r"(\s+)", dumped)
    other_tokens = re.split(r"(\s+)", other_dumped)
    matcher = difflib.SequenceMatcher(None, tokens, other_tokens, autojunk=False)
    segments = [_Segment('"', color=color)]
    for tag, start, end, _, _ in matcher.get_opcodes():
        text = "".join(tokens[start:end])
        if text:
            segments.append(_Segment(text, color=color, chip=tag != "equal"))
    segments.append(_Segment('"', color=color))
    return tuple(segments)


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
    chip: str | None = None,
    other_value: object = None,
) -> list[_PaneLine]:
    """One side's lines for a PARAM row; empty when the side lacks the key
    (the caller pads with gap blocks to keep the panes aligned).

    *chip* is the side's value-chip mode: ``None`` (no chip), ``"whole"``
    (chip the whole rendered value) or ``"tokens"`` (string values only:
    chip just the tokens that differ from *other_value*). Open dict/list
    values ignore it -- their chips come from the line alignment instead.
    """
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
                        _Segment(
                            _CLOSED_SUMMARY,
                            color=style.MUTED,
                            italic=True,
                            chip=chip is not None,
                        ),
                    ),
                    depth=row.depth,
                    caret=_CARET_CLOSED,
                )
            ]
        return _open_value_panes(row.key, value, row.depth, color)
    prefix = _Segment(f'"{row.key}": ', color=color)
    if chip == "tokens" and isinstance(value, str) and isinstance(other_value, str):
        return [
            _PaneLine(
                segments=(prefix,) + _token_diff_segments(value, other_value, color),
                depth=row.depth,
            )
        ]
    return [
        _PaneLine(
            segments=(
                prefix,
                _Segment(format_value(value), color=color, chip=chip is not None),
            ),
            depth=row.depth,
        )
    ]


def _chip_pane(pane: _PaneLine) -> _PaneLine:
    return _PaneLine(
        segments=tuple(
            _Segment(s.text, s.color, s.bold, s.italic, True) for s in pane.segments
        ),
        depth=pane.depth,
        caret=pane.caret,
    )


def _align_panes(
    main_panes: list[_PaneLine],
    ref_panes: list[_PaneLine],
    depth: int,
    chip_replaced: bool = False,
) -> list[tuple[_PaneLine, _PaneLine]]:
    """Pair one parameter's two sides line by line: identical JSON lines
    pair up, unmatched lines face a gap block -- so a longer table pads
    beside its extra entries, inside the table, never at its tail.

    With *chip_replaced* (open dict/list values), the entry lines that
    genuinely changed -- paired but different beyond a trailing comma --
    chip on both sides: the frames' per-table-entry chips. Extra entries
    facing a gap do not chip (the gap already carries the signal), and key
    lines (carets) never chip.
    """
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
                main = main_panes[m1 + offset] if m1 + offset < m2 else gap
                ref = ref_panes[r1 + offset] if r1 + offset < r2 else gap
                if (
                    tag == "replace"
                    and chip_replaced
                    and not main.gap
                    and not ref.gap
                    and main.caret is None
                    and ref.caret is None
                    and main.text.rstrip(",") != ref.text.rstrip(",")
                ):
                    main, ref = _chip_pane(main), _chip_pane(ref)
                pairs.append((main, ref))
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
    # Sections holding any difference (differs/fillable/ref-only anywhere
    # beneath, ref-only ghost sections included): their collapsed headers
    # carry the chipped ⋯. Ancestors only -- a ref-only header itself stays
    # purple-without-chip, per the signed frames.
    diff_sections: set[tuple[str, ...]] = set()
    if two_pane:
        for row in rows:
            if row.is_difference:
                for depth in range(1, len(row.path)):
                    diff_sections.add(row.path[:depth])
    lines: list[_Line] = []
    for row in rows:
        # Anything under a closed section stays unrendered, on both sides.
        if any(row.path[:n] in closed for n in range(1, len(row.path))):
            continue
        is_closed = row.path in closed
        if row.kind is RowKind.SECTION:
            # The ⋯ chip belongs to shared collapsed sections only: a
            # ref-only header is already purple, a main-only section can
            # never contain differences.
            diff_dots = (
                is_closed
                and row.in_main
                and row.in_reference
                and row.path in diff_sections
            )
            main = (
                _section_pane(
                    row,
                    style.DEFAULT_TEXT,
                    counts_main.get(row.path, 0),
                    is_closed,
                    diff_dots,
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
                        row,
                        key_color,
                        counts_ref.get(row.path, 0),
                        is_closed,
                        diff_dots,
                    )
                    if row.in_reference
                    else _gap(row.depth)
                )
            lines.append(
                _Line(
                    main=main,
                    ref=ref,
                    toggle_path=row.path,
                    # ← on a section header only when the whole section is
                    # ref-only: its pull copies the full subtree, one undo
                    # entry (frames: "State"; shared headers carry no ←).
                    pull_path=row.path
                    if two_pane and row.is_difference
                    else None,
                    pull_section=two_pane and row.is_difference,
                )
            )
        else:
            # Value-chip modes per state (signed frames): differs chips
            # both sides -- token-level for string pairs, whole otherwise;
            # fillable chips the reference-side value alone; everything
            # else (equal, main-only, ref-only) carries no chip.
            chip = None
            if two_pane and row.state is RowState.DIFFERS:
                both_str = isinstance(row.main_value, str) and isinstance(
                    row.ref_value, str
                )
                chip = "tokens" if both_str else "whole"
            main_panes = _param_side_panes(
                row,
                row.main_value,
                row.in_main,
                style.DEFAULT_TEXT,
                two_pane and row.state is RowState.FILLABLE,
                is_closed,
                chip=chip,
                other_value=row.ref_value,
            )
            if two_pane:
                value_color = (
                    style.REFERENCE
                    if row.state is RowState.REF_ONLY
                    else style.DEFAULT_TEXT
                )
                ref_chip = chip
                if row.state is RowState.FILLABLE:
                    ref_chip = "whole"
                ref_panes = _param_side_panes(
                    row,
                    row.ref_value,
                    row.in_reference,
                    value_color,
                    False,
                    is_closed,
                    chip=ref_chip,
                    other_value=row.main_value,
                )
                for index, (main, ref) in enumerate(
                    _align_panes(
                        main_panes,
                        ref_panes,
                        row.depth,
                        chip_replaced=row.closable and not is_closed,
                    )
                ):
                    lines.append(
                        _Line(
                            main=main,
                            ref=ref,
                            toggle_path=row.path
                            if index == 0 and row.closable
                            else None,
                            # ← on the parameter's key line; its pull always
                            # copies the whole value, table or scalar.
                            pull_path=row.path
                            if index == 0 and row.is_difference
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

    Painting the ← chip is the view's job; *acting* on it is not: a gutter
    click only emits :attr:`pull_requested` (path, is_section) and the
    window layer runs the shared M3 command -- the page itself never
    mutates the document (coexistence rule 14).
    """

    #: A ← gutter chip was clicked: (path, is_section).
    pull_requested = Signal(object, bool)

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

    def pull_lines(self) -> list[tuple[int, tuple[str, ...], bool]]:
        """Every line carrying a ← gutter chip as ``(line index, path,
        is_section)`` -- the test-facing read of the pull affordances."""
        return [
            (index, line.pull_path, line.pull_section)
            for index, line in enumerate(self._lines)
            if line.pull_path is not None
        ]

    def chipped_texts(self) -> list[tuple[int, str, str]]:
        """Every chip-highlighted segment as ``(line index, "main"/"ref",
        text)`` -- the test-facing read of the value chips."""
        found: list[tuple[int, str, str]] = []
        for index, line in enumerate(self._lines):
            for side, pane in (("main", line.main), ("ref", line.ref)):
                if pane is None or pane.gap:
                    continue
                for segment in pane.segments:
                    if segment.chip:
                        found.append((index, side, segment.text))
        return found

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
            if self._two_pane and line.pull_path is not None:
                self._paint_pull_chip(painter, pane_width, top, line_height)
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
            advance = painter.fontMetrics().horizontalAdvance(segment.text)
            if segment.chip:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(style.DIFF_TINT))
                painter.drawRoundedRect(
                    x - 2, top + 2, advance + 4, line_height - 4, 3, 3
                )
                painter.setBrush(Qt.NoBrush)
            painter.setPen(QColor(segment.color))
            painter.drawText(x, baseline, segment.text)
            x += advance
        painter.restore()

    def _paint_pull_chip(
        self, painter: QPainter, pane_width: int, top: int, line_height: int
    ) -> None:
        """The ← copy affordance, centred in the gutter column: light
        purple tint, pointing into the main file (frames F1/F2)."""
        x = pane_width + (_GUTTER_PX - _PULL_W) // 2
        y = top + (line_height - _PULL_H) // 2
        painter.setPen(QColor(style.REFERENCE_BORDER))
        painter.setBrush(QColor(style.REFERENCE_TINT))
        painter.drawRoundedRect(x, y, _PULL_W, _PULL_H, 4, 4)
        painter.setBrush(Qt.NoBrush)
        painter.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        painter.setPen(QColor(style.REFERENCE))
        painter.drawText(
            x,
            y,
            _PULL_W,
            _PULL_H,
            Qt.AlignCenter,
            _PULL_GLYPH,
        )

    # -- interaction -----------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        point = event.position().toPoint()
        index = (point.y() + self.verticalScrollBar().value()) // self._line_height()
        if 0 <= index < len(self._lines):
            line = self._lines[int(index)]
            pane_width = self._pane_width()
            in_gutter = (
                self._two_pane and pane_width <= point.x() < pane_width + _GUTTER_PX
            )
            if in_gutter:
                # The gutter is the ←'s territory alone: no pull chip on
                # this line means the click does nothing (never a stray
                # fold toggle).
                if line.pull_path is not None:
                    self.pull_requested.emit(line.pull_path, line.pull_section)
                return
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

    #: Re-emitted from the view's ← gutter clicks: (path, is_section).
    #: MainWindow runs the shared pull command; the page never mutates.
    pull_requested = Signal(object, bool)

    def __init__(self) -> None:
        super().__init__()
        self._view = SourceView()
        self._view.pull_requested.connect(self.pull_requested)

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
