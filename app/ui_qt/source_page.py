"""Source page: the document's formatted raw JSON, live against the session.

With no reference docked the page shows one full-width pane of the main
file -- monospace, collapsible section headers, "n parameters" sizes, and a
quiet identity-strip hint that docking a reference turns the page into a
split comparison. With a reference docked the same rows render as two panes
aligned line by line: a centre gutter column separates them, a flat grey
block marks a key one side lacks, reference-only rows read in the
reference purple, and fillable keys grey out with no value. Section and
table folding is shared -- one caret folds both panes together.

The page never edits: it contains no input widget, ever. All content is
painted by :class:`SourceView`, a custom scroll area over
:func:`core.source_rows.build_rows` -- deliberately not entangled with
``BpxTreeModel``: the Source page owns its own row/fold state.
"""

from __future__ import annotations

import bisect
import difflib
import json
import re
from dataclasses import dataclass, replace

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.compare import RowState
from core.source_rows import RowKind, SourceRow, build_rows, format_value
from ui_qt import badges, style, typography
from ui_qt.elided_label import ElidedLabel

#: One indent step, in pixels, per nesting depth.
_INDENT_PX = 18
#: Left margin before depth-0 text; also the caret column's width.
_LEFT_MARGIN = 10
#: Vertical padding added to the font's line height.
_LINE_PADDING = 6
#: The centre column between the two panes; the ← copy affordances land
#: here in a later step, the width is reserved now so the layout is stable.
_GUTTER_PX = 40
#: Breathing room at a pane's right edge, before text wraps.
_RIGHT_PADDING = 12
#: Hanging indent for a wrapped line's continuation rows, so a long value
#: reads as one line's overflow rather than a new key.
_WRAP_INDENT = _INDENT_PX
#: A continuation row never narrows past this, however deep the nesting or
#: however cramped the pane -- below it, wrapping degenerates.
_MIN_WRAP_WIDTH = 60

_CARET_OPEN = "▾"
_CARET_CLOSED = "▸"
_PULL_GLYPH = "←"
#: The ← chip's box inside the gutter column (the frames' 26×20 rounded
#: rect, centred).
_PULL_W = 26
_PULL_H = 20

#: The one-line stand-in for a closed dict/list value.
_CLOSED_SUMMARY = "table"

#: How long the just-pulled row's gutter shows its "Used" tag. Long
#: enough to register where the eye already is, short enough that a
#: next-pull rhythm never shows a stale tag.
_PULLED_FLASH_MS = 2500


@dataclass(frozen=True)
class _Segment:
    """One run of same-styled text within a line."""

    text: str
    color: str = style.DEFAULT_TEXT
    bold: bool = False
    italic: bool = False
    #: Painted over the ``style.DIFF_TINT`` wash: the value-only highlight
    #: chip. Only values (or the ⋯/"table" stand-ins) ever chip -- keys,
    #: structure and whole rows never do.
    chip: bool = False


def _same_style(a: _Segment, b: _Segment) -> bool:
    """Whether two segments paint identically -- adjacent runs that do are
    merged back together after wrapping."""
    return (a.color, a.bold, a.italic, a.chip) == (b.color, b.bold, b.italic, b.chip)


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
    #: header -- absent entirely on equal and main-only rows, and on
    #: shared section headers.
    pull_path: tuple[str, ...] | None = None
    pull_section: bool = False
    #: The owning row's path, set on the row's first painted line only (a
    #: parameter's key line, a section's header line). This is the line the
    #: selection outline anchors to: arrow-key navigation and row clicks
    #: select by path, so the selection survives re-renders and fold changes.
    row_path: tuple[str, ...] | None = None


@dataclass(frozen=True)
class _Block:
    """One logical :class:`_Line` as laid out for painting: each pane's
    wrapped rows, and the shared row count both sides occupy.

    A wrapped line still occupies one block, so the panes stay aligned line
    by line: the block is as tall as the taller side's wrap, and a gap
    block fills the whole of it.
    """

    main_rows: tuple[tuple[_Segment, ...], ...]
    ref_rows: tuple[tuple[_Segment, ...], ...] | None
    rows: int
    top: int


def _gap(depth: int) -> _PaneLine:
    return _PaneLine(depth=depth, gap=True)


def _param_counts(rows: list[SourceRow], present) -> dict[tuple[str, ...], int]:
    """Per-section count of parameter rows beneath it, counting only rows
    the *present* predicate admits -- so each pane's header counts its own
    side's parameters."""
    counts: dict[tuple[str, ...], int] = {row.path: 0 for row in rows if row.kind is RowKind.SECTION}
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
        # differs, is fillable or is ref-only. No text counts here -- the
        # chip alone carries the signal.
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
    tail is shared."""
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


def _open_value_panes(key: str, value: object, depth: int, color: str) -> list[_PaneLine]:
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
        panes.append(_PaneLine(segments=(_Segment(stripped, color=color),), depth=depth + extra))
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
        # Fillable rendering: grey key, no value -- the slot is there,
        # nothing meaningful fills it yet.
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
        segments=tuple(_Segment(s.text, s.color, s.bold, s.italic, True) for s in pane.segments),
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
    chip on both sides. Extra entries facing a gap do not chip (the gap
    already carries the signal), and key lines (carets) never chip.
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
    rows: list[SourceRow],
    closed: set[tuple[str, ...]],
    two_pane: bool,
    pull_enabled: bool = True,
) -> list[_Line]:
    counts_main = _param_counts(rows, lambda row: row.in_main)
    counts_ref = _param_counts(rows, lambda row: row.in_reference) if two_pane else {}
    # Sections holding any difference (differs/fillable/ref-only anywhere
    # beneath, ref-only ghost sections included): their collapsed headers
    # carry the chipped ⋯. Ancestors only -- a ref-only header itself stays
    # purple-without-chip.
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
            diff_dots = is_closed and row.in_main and row.in_reference and row.path in diff_sections
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
                key_color = style.REFERENCE if not row.in_main else style.DEFAULT_TEXT
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
                    # ref-only: its pull copies the full subtree as one undo
                    # entry; shared headers carry no ← -- and a read-only
                    # main (pull_enabled False) offers none anywhere.
                    pull_path=row.path if pull_enabled and two_pane and row.is_difference else None,
                    pull_section=pull_enabled and two_pane and row.is_difference,
                    row_path=row.path,
                )
            )
        else:
            # Value-chip modes per state: differs chips
            # both sides -- token-level for string pairs, whole otherwise;
            # fillable chips the reference-side value alone; everything
            # else (equal, main-only, ref-only) carries no chip.
            chip = None
            if two_pane and row.state is RowState.DIFFERS:
                both_str = isinstance(row.main_value, str) and isinstance(row.ref_value, str)
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
                value_color = style.REFERENCE if row.state is RowState.REF_ONLY else style.DEFAULT_TEXT
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
                            toggle_path=row.path if index == 0 and row.closable else None,
                            # ← on the parameter's key line; its pull always
                            # copies the whole value, table or scalar.
                            pull_path=row.path if pull_enabled and index == 0 and row.is_difference else None,
                            row_path=row.path if index == 0 else None,
                        )
                    )
            else:
                for index, main in enumerate(main_panes):
                    lines.append(
                        _Line(
                            main=main,
                            toggle_path=row.path if index == 0 and row.closable else None,
                            row_path=row.path if index == 0 else None,
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
    window layer runs the shared pull command -- the page itself never
    mutates the document.
    """

    #: A ← gutter chip was clicked: (path, is_section).
    pull_requested = Signal(object, bool)
    #: A row was double-clicked: its path, for the Editor jump
    #: through ``NavigationService``. Emitted only for rows the main
    #: document actually has -- a ref-only row names nothing the Editor
    #: could resolve, and suffix-matching must never guess for it.
    navigate_requested = Signal(object)
    #: Emitted whenever the fold state changes -- individual toggles, or
    #: the toolbar's fold-all button -- so the toolbar label can track the
    #: view's aggregate state without every caller telling it explicitly.
    fold_state_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[SourceRow] = []
        self._two_pane = False
        self._closed: set[tuple[str, ...]] = set()
        self._lines: list[_Line] = []
        #: The selected row's path, or ``None``. Selection is by path, not
        #: line index, so it survives re-renders, folds and edits; arrow
        #: keys move it and a row click places it directly.
        self._selected: tuple[str, ...] | None = None
        #: False while the main document is read-only: rows render
        #: without their ← pull affordance. Refreshed by every set_rows.
        self._pull_enabled = True
        #: The just-pulled row's path while its gutter "Used" tag shows
        #: (the stay-put confirmation after a pull); cleared by the
        #: single-shot timer, or by ``set_rows`` if the row itself vanishes
        #: (undo).
        self._flash_path: tuple[str, ...] | None = None
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_flash)
        #: Font metrics per (bold, italic) variant of the fixed font -- text
        #: is measured for wrapping far more often than it is painted.
        self._metrics_cache: dict[tuple[bool, bool], QFontMetrics] = {}
        #: The painted layout: one block per line, rebuilt whenever the
        #: lines or the pane width change.
        self._blocks: list[_Block] = []
        self._tops: list[int] = []
        self._content_height = 0
        #: Pane width the current layout was wrapped for; a mismatch means
        #: the layout is stale and re-wraps on next use.
        self._layout_width = -1
        # Focusable for Up/Down row navigation -- still never an input
        # widget: keys move the selection, nothing edits.
        self.setFocusPolicy(Qt.StrongFocus)
        # Long values wrap at the pane edge instead of running off it: with
        # two panes there is no width to spare, and nothing here is edited,
        # so a horizontal scrollbar would only hide content.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    # -- content ---------------------------------------------------------

    def set_rows(
        self,
        rows: list[SourceRow],
        two_pane: bool = False,
        pull_enabled: bool = True,
    ) -> None:
        """Replace the rendered rows, pruning fold state for paths that no
        longer exist (a removed section must not haunt the closed set).
        ``pull_enabled`` False (a read-only main) renders every row
        without its ← pull affordance."""
        self._rows = rows
        self._two_pane = two_pane
        self._pull_enabled = pull_enabled
        foldable = {row.path for row in rows if row.kind is RowKind.SECTION or row.closable}
        self._closed &= foldable
        # A selection whose row vanished (edit, undo, reference change) is
        # dropped rather than left pointing at nothing.
        if self._selected is not None and self._selected not in {row.path for row in rows}:
            self._selected = None
        # A pulled row survives its own re-render (it merely turns equal),
        # but an undo removes it -- take the tag with it.
        if self._flash_path is not None and self._flash_path not in {row.path for row in rows}:
            self._clear_flash()
        self._rebuild()

    def flash_pulled(self, path: tuple[str, ...]) -> None:
        """Show the transient "Used" tag in *path*'s gutter slot -- the
        stay-put confirmation of a completed ← pull. One at a time: a new
        pull moves the tag and restarts its clock."""
        self._flash_path = tuple(path)
        self._flash_timer.start(_PULLED_FLASH_MS)
        self.viewport().update()

    def flash_path(self) -> tuple[str, ...] | None:
        """The row currently showing the "Used" tag, or ``None``
        (test/driver read)."""
        return self._flash_path

    def _clear_flash(self) -> None:
        self._flash_timer.stop()
        self._flash_path = None
        self.viewport().update()

    def toggle_fold(self, path: tuple[str, ...]) -> None:
        """Fold/unfold the section or closable value at *path* -- in both
        panes at once (shared fold state)."""
        if path in self._closed:
            self._closed.discard(path)
        else:
            self._closed.add(path)
        self._rebuild()

    # -- selection & fold-all ---------------------------------------------

    def selected_path(self) -> tuple[str, ...] | None:
        """The selected row's path, or ``None`` (test/driver read)."""
        return self._selected

    def all_tables_expanded(self) -> bool:
        """Whether every closable table is currently open -- the toolbar's
        fold-all button reads this to choose its label. Sections don't
        count: the button acts on tables only."""
        return not any(row.closable and row.path in self._closed for row in self._rows)

    def set_tables_folded(self, folded: bool) -> None:
        """Fold every closable table (``True``) or unfold all of them
        (``False``) -- the toolbar's fold-all button, always a flat
        all-or-nothing action rather than restoring each row's prior
        state. Section folds are left exactly as the user set them."""
        tables = {row.path for row in self._rows if row.closable}
        if folded:
            self._closed |= tables
        else:
            self._closed -= tables
        self._rebuild()

    def reveal(self, path: tuple[str, ...]) -> None:
        """Select the row at *path*, unfolding any closed ancestor section
        and scrolling its key line into view (a closed table's own key
        line is already visible, so only ancestors ever unfold)."""
        for depth in range(1, len(path)):
            self._closed.discard(path[:depth])
        self._selected = path
        self._rebuild()
        self._scroll_to(path)
        self.viewport().update()

    def _scroll_to(self, path: tuple[str, ...]) -> None:
        """Scroll *path*'s key line into the viewport if it is not already
        visible (centred, so a jump shows its surroundings too)."""
        line_height = self._line_height()
        for index, line in enumerate(self._lines):
            if line.row_path == path:
                top = self.line_top(index)
                height = self.line_rows(index) * line_height
                bar = self.verticalScrollBar()
                view_height = self.viewport().height()
                if not bar.value() <= top <= bar.value() + view_height - height:
                    bar.setValue(max(0, top - view_height // 2))
                break

    def move_selection(self, delta: int) -> None:
        """Move the selection one visible row up (-1) or down (+1).

        Walks the rows as rendered (a folded section's children are not
        visited; open-value continuation lines are skipped) and stops at
        the ends -- arrows do not wrap. With nothing selected, Down starts
        at the first row and Up at the last.
        """
        row_paths = [line.row_path for line in self._lines if line.row_path is not None]
        if not row_paths:
            return
        if self._selected in row_paths:
            index = row_paths.index(self._selected) + delta
            if not 0 <= index < len(row_paths):
                return
        else:
            index = 0 if delta > 0 else len(row_paths) - 1
        self._selected = row_paths[index]
        self._scroll_to(self._selected)
        self.viewport().update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Up:
            self.move_selection(-1)
            event.accept()
            return
        if event.key() == Qt.Key_Down:
            self.move_selection(+1)
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            # Enter pulls the selected row -- the keyboard counterpart of
            # its ← chip. A row with no chip ignores the key: equal
            # and main-only rows stay as impossible to pull as ever.
            line = next(
                (
                    candidate
                    for candidate in self._lines
                    if candidate.row_path is not None and candidate.row_path == self._selected
                ),
                None,
            )
            if line is not None and line.pull_path is not None:
                self.pull_requested.emit(line.pull_path, line.pull_section)
            event.accept()
            return
        super().keyPressEvent(event)

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
                found.extend((index, side, segment.text) for segment in pane.segments if segment.chip)
        return found

    # -- geometry --------------------------------------------------------

    def _line_height(self) -> int:
        # Measured on the fixed font the lines are actually painted with,
        # not the widget's UI font.
        return self._metrics(False, False).height() + _LINE_PADDING

    def _metrics(self, bold: bool, italic: bool) -> QFontMetrics:
        key = (bold, italic)
        if key not in self._metrics_cache:
            weight = typography.SEMIBOLD if bold else typography.REGULAR
            font = typography.mono(typography.BODY, weight=weight, slanted=italic)
            self._metrics_cache[key] = QFontMetrics(font)
        return self._metrics_cache[key]

    def _advance(self, text: str, segment: _Segment) -> int:
        return self._metrics(segment.bold, segment.italic).horizontalAdvance(text)

    def _pane_width(self) -> int:
        if not self._two_pane:
            return self.viewport().width()
        return max(0, (self.viewport().width() - _GUTTER_PX) // 2)

    def _pane_x(self, pane: _PaneLine) -> int:
        return _LEFT_MARGIN + pane.depth * _INDENT_PX + 14

    def _wrap_x(self, pane: _PaneLine, row: int) -> int:
        """A wrapped row's left offset within its pane: the line's own
        indent, plus one hanging step on every continuation row."""
        return self._pane_x(pane) + (_WRAP_INDENT if row else 0)

    def _wrap_pane(self, pane: _PaneLine) -> tuple[tuple[_Segment, ...], ...]:
        """Break one pane line's segments into rows that fit the pane.

        Wrapping prefers whitespace and falls back to breaking mid-token
        only when a single token is wider than the row (a long unbroken
        number or identifier). Styling is preserved, and tokens that land
        on the same row are merged back into one segment so a chipped run
        still paints as a single rounded chip per row.
        """
        pane_width = self._pane_width()
        widths = [max(_MIN_WRAP_WIDTH, pane_width - self._wrap_x(pane, row) - _RIGHT_PADDING) for row in (0, 1)]
        rows: list[tuple[_Segment, ...]] = []
        current: list[_Segment] = []
        used = 0
        width = widths[0]

        def flush() -> None:
            nonlocal current, used, width
            rows.append(tuple(current))
            current = []
            used = 0
            width = widths[1]

        def add(text: str, segment: _Segment) -> None:
            nonlocal used
            if current and _same_style(current[-1], segment):
                current[-1] = replace(current[-1], text=current[-1].text + text)
            else:
                current.append(replace(segment, text=text))
            used += self._advance(text, segment)

        for segment in pane.segments:
            if not segment.text:
                continue
            if used + self._advance(segment.text, segment) <= width:
                add(segment.text, segment)
                continue
            for token in re.split(r"(\s+)", segment.text):
                if not token:
                    continue
                token_width = self._advance(token, segment)
                if used + token_width > width and current:
                    flush()
                    # A row never opens on the whitespace it wrapped at.
                    if token.isspace():
                        continue
                if token_width <= width:
                    add(token, segment)
                    continue
                for char in token:
                    char_width = self._advance(char, segment)
                    if used + char_width > width and current:
                        flush()
                    add(char, segment)
        flush()
        return tuple(rows)

    def _rebuild(self) -> None:
        self._lines = _build_lines(self._rows, self._closed, self._two_pane, self._pull_enabled)
        self._relayout()
        self.viewport().update()
        self.fold_state_changed.emit()

    def _ensure_layout(self) -> None:
        """Re-wrap if the pane width has moved since the last layout.

        Laying out lazily rather than on the resize event keeps the wrap
        honest whatever the widget's state: a viewport that resizes without
        delivering an event (offscreen, or before the first show) still
        paints and hit-tests against the width it actually has.
        """
        if self._layout_width != self._pane_width():
            self._relayout()

    def _relayout(self) -> None:
        """Wrap every line at the current pane width and stack the blocks."""
        line_height = self._line_height()
        self._layout_width = self._pane_width()
        blocks: list[_Block] = []
        tops: list[int] = []
        top = 0
        for line in self._lines:
            main_rows = () if line.main.gap else self._wrap_pane(line.main)
            ref_rows = None
            if line.ref is not None:
                ref_rows = () if line.ref.gap else self._wrap_pane(line.ref)
            count = max(1, len(main_rows), len(ref_rows or ()))
            blocks.append(_Block(main_rows, ref_rows, count, top))
            tops.append(top)
            top += count * line_height
        self._blocks = blocks
        self._tops = tops
        self._content_height = top
        self._update_scrollbars()

    def line_top(self, index: int) -> int:
        """Content-coordinate top of line *index* -- the wrap-aware
        replacement for ``index * line_height`` (test/driver read)."""
        self._ensure_layout()
        if 0 <= index < len(self._blocks):
            return self._blocks[index].top
        return index * self._line_height()

    def line_rows(self, index: int) -> int:
        """How many painted rows line *index* wrapped onto (test read)."""
        self._ensure_layout()
        if 0 <= index < len(self._blocks):
            return self._blocks[index].rows
        return 1

    def _line_at(self, y: int) -> int:
        """Index of the line whose block contains content-coordinate *y*,
        or -1 above the first line / below the last."""
        self._ensure_layout()
        if not self._tops or y < 0 or y >= self._content_height:
            return -1
        return bisect.bisect_right(self._tops, y) - 1

    def _update_scrollbars(self) -> None:
        line_height = self._line_height()
        self.verticalScrollBar().setRange(0, max(0, self._content_height - self.viewport().height()))
        self.verticalScrollBar().setSingleStep(line_height)
        self.verticalScrollBar().setPageStep(self.viewport().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # A narrower pane moves every wrap point; the height alone only
        # changes how much of the layout fits on screen.
        self._ensure_layout()
        self._update_scrollbars()

    # -- painting --------------------------------------------------------

    def paintEvent(self, event) -> None:
        self._ensure_layout()
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor("#ffffff"))
        line_height = self._line_height()
        v_offset = self.verticalScrollBar().value()
        pane_width = self._pane_width()
        first = max(0, self._line_at(v_offset))
        bottom = v_offset + self.viewport().height()
        ascent = (line_height + self._metrics(False, False).ascent()) // 2 - 2
        for index in range(first, len(self._lines)):
            line = self._lines[index]
            block = self._blocks[index]
            if block.top >= bottom:
                break
            top = block.top - v_offset
            block_height = block.rows * line_height
            self._paint_pane(
                painter,
                line.main,
                block.main_rows,
                0,
                pane_width,
                top,
                ascent,
                block_height,
                line_height,
            )
            if line.ref is not None:
                self._paint_pane(
                    painter,
                    line.ref,
                    block.ref_rows or (),
                    pane_width + _GUTTER_PX,
                    pane_width,
                    top,
                    ascent,
                    block_height,
                    line_height,
                )
            if self._two_pane and line.pull_path is not None:
                self._paint_pull_chip(painter, pane_width, top, line_height)
            elif self._two_pane and line.row_path is not None and line.row_path == self._flash_path:
                # The pulled row's chip is gone (it is equal now); its
                # gutter slot briefly says what just happened instead.
                self._paint_pulled_tag(painter, pane_width, top, line_height)
            if line.row_path is not None and line.row_path == self._selected:
                # The frames' selection: a thin accent outline on the row's
                # pane cell(s) -- both panes in two-pane mode, never the
                # gutter between them.
                painter.setPen(QColor(style.ACCENT))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(0, top, pane_width - 1, block_height - 1)
                if self._two_pane:
                    painter.drawRect(
                        pane_width + _GUTTER_PX,
                        top,
                        pane_width - 1,
                        block_height - 1,
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
        rows: tuple[tuple[_Segment, ...], ...],
        x0: int,
        width: int,
        top: int,
        ascent: int,
        block_height: int,
        line_height: int,
    ) -> None:
        if pane.gap:
            # The absent side fills the whole block, however far the other
            # side's value wrapped.
            painter.fillRect(x0, top, width, block_height, QColor(style.NEUTRAL_TINT))
            return
        painter.save()
        painter.setClipRect(x0, top, width, block_height)
        if pane.caret is not None:
            painter.setFont(typography.mono(typography.BODY))
            painter.setPen(QColor(style.MUTED))
            caret_x = x0 + _LEFT_MARGIN + pane.depth * _INDENT_PX
            painter.drawText(caret_x, top + ascent, pane.caret)
        for row, segments in enumerate(rows):
            row_top = top + row * line_height
            baseline = row_top + ascent
            x = x0 + self._wrap_x(pane, row)
            for segment in segments:
                weight = typography.SEMIBOLD if segment.bold else typography.REGULAR
                font = typography.mono(typography.BODY, weight=weight, slanted=segment.italic)
                painter.setFont(font)
                advance = painter.fontMetrics().horizontalAdvance(segment.text)
                if segment.chip:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(style.DIFF_TINT))
                    painter.drawRoundedRect(x - 2, row_top + 2, advance + 4, line_height - 4, 3, 3)
                    painter.setBrush(Qt.NoBrush)
                painter.setPen(QColor(segment.color))
                painter.drawText(x, baseline, segment.text)
                x += advance
        painter.restore()

    def _paint_pull_chip(self, painter: QPainter, pane_width: int, top: int, line_height: int) -> None:
        """The ← copy affordance, centred in the gutter column: light
        purple tint, pointing into the main file."""
        x = pane_width + (_GUTTER_PX - _PULL_W) // 2
        y = top + (line_height - _PULL_H) // 2
        painter.setPen(QColor(style.REFERENCE_BORDER))
        painter.setBrush(QColor(style.REFERENCE_TINT))
        painter.drawRoundedRect(x, y, _PULL_W, _PULL_H, 4, 4)
        painter.setBrush(Qt.NoBrush)
        painter.setFont(typography.mono(typography.BODY))
        painter.setPen(QColor(style.REFERENCE))
        painter.drawText(
            x,
            y,
            _PULL_W,
            _PULL_H,
            Qt.AlignCenter,
            _PULL_GLYPH,
        )

    def _paint_pulled_tag(self, painter: QPainter, pane_width: int, top: int, line_height: int) -> None:
        """The transient "Used" confirmation, in the ← chip's own slot
        and palette -- a role word, not a glyph."""
        width = _GUTTER_PX - 4
        x = pane_width + (_GUTTER_PX - width) // 2
        y = top + (line_height - _PULL_H) // 2
        painter.setPen(QColor(style.REFERENCE_BORDER))
        painter.setBrush(QColor(style.REFERENCE_TINT))
        painter.drawRoundedRect(x, y, width, _PULL_H, 4, 4)
        painter.setBrush(Qt.NoBrush)
        font = typography.mono(typography.MICRO, weight=typography.SEMIBOLD)
        painter.setFont(font)
        painter.setPen(QColor(style.REFERENCE))
        painter.drawText(x, y, width, _PULL_H, Qt.AlignCenter, "Used")

    # -- interaction -----------------------------------------------------

    def mousePressEvent(self, event) -> None:
        point = event.position().toPoint()
        index = self._line_at(point.y() + self.verticalScrollBar().value())
        if index >= 0:
            line = self._lines[index]
            pane_width = self._pane_width()
            in_gutter = self._two_pane and pane_width <= point.x() < pane_width + _GUTTER_PX
            if in_gutter:
                # The gutter is the ←'s territory alone: no pull chip on
                # this line means the click does nothing (never a stray
                # fold toggle).
                if line.pull_path is not None:
                    self.pull_requested.emit(line.pull_path, line.pull_section)
                return
            # A pane click places the selection on the clicked row (its key
            # line carries the path; continuation lines of an open value
            # leave the selection where it is).
            if line.row_path is not None and line.row_path != self._selected:
                self._selected = line.row_path
                self.viewport().update()
            if line.toggle_path is not None:
                self.toggle_fold(line.toggle_path)
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click a row: jump to it in the Editor.

        Pane cells only -- the gutter stays the ←'s territory (its press
        already pulled once; a double-click must not pull twice or jump).
        Only rows the main document has are emitted: a ref-only row names
        nothing the Editor could reveal, so it stays a Source-page fact.
        """
        point = event.position().toPoint()
        index = self._line_at(point.y() + self.verticalScrollBar().value())
        if index >= 0:
            line = self._lines[index]
            pane_width = self._pane_width()
            in_gutter = self._two_pane and pane_width <= point.x() < pane_width + _GUTTER_PX
            if not in_gutter and line.row_path is not None:
                row = next((r for r in self._rows if r.path == line.row_path), None)
                if row is not None and row.in_main:
                    self.navigate_requested.emit(line.row_path)
                    return
        super().mouseDoubleClickEvent(event)


class SourcePage(QWidget):
    """The Source rail page: identity strip + pane headers + the raw-JSON
    view (one pane, or two aligned panes with a reference docked). Its
    fold-all toggle is built here but docked by MainWindow into the shared
    page-header bar, right-locked beside the page title."""

    #: Re-emitted from the view's ← gutter clicks: (path, is_section).
    #: MainWindow runs the shared pull command; the page never mutates.
    pull_requested = Signal(object, bool)
    #: The stale band's Reload link: re-snapshot the reference from disk.
    reload_requested = Signal()
    #: A row was double-clicked: jump to it in the Editor. The
    #: page re-emits; MainWindow routes through ``NavigationService``.
    navigate_requested = Signal(object)
    #: The pane-header selector chose a different pinned reference (its pin
    #: index). MainWindow re-renders the page against it; everything the
    #: page does -- the comparison, Reload, the ← pull arrows -- then acts on
    #: that reference and no other.
    reference_selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        #: Which pinned reference the reference pane shows. Pin index, not a
        #: snapshot: the pin list is rebuilt on every change, and an index
        #: survives that where an object identity would not.
        self._selected_reference = 0
        self._view = SourceView()
        self._view.pull_requested.connect(self.pull_requested)
        self._view.navigate_requested.connect(self.navigate_requested)

        # Fold-all toggle: built and driven here (its label tracks the
        # view's table fold state) but never laid out here -- MainWindow
        # docks it into the page-header bar's trailing slot, the same
        # docking the Editor's comparison chips use, so it sits right-locked
        # in the bar that names the page. It acts on closable tables only
        # (sections fold via their own carets); label and caret follow
        # ``fold_state_changed`` -- "Expand" whenever any table is folded,
        # "Collapse" only once every table is open. Shown only while the
        # Source page is current *and* a document is open: the bar is shared
        # by every page, so ``set_page_active`` must gate what ``refresh``
        # alone cannot know.
        self._fold_button = QPushButton()
        self._fold_button.setObjectName("SourceFoldButton")
        self._fold_button.clicked.connect(self._on_fold_toggle)
        self._view.fold_state_changed.connect(self._update_fold_button)
        self._update_fold_button()
        self._has_document = False
        #: True by default, exactly like ComparisonStrip: a bare page (unit
        #: tests) is its own current page; MainWindow corrects it on every
        #: page switch.
        self._page_active = True
        self._update_fold_visible()

        # Single-pane identity strip: the main file's name in the defined
        # semibold every other identity surface uses (the board's main
        # card, the comparison chips), its model as a muted detail beside
        # it, and the docking hint on the right. All single-pane chrome:
        # two-pane mode replaces the strip with the pane headers.
        # Name and hint elide under pressure; the model detail never does.
        self._file_label = ElidedLabel("SourceFileName")
        self._file_model = QLabel()
        self._file_model.setObjectName("SourceFileModel")
        self._hint = ElidedLabel("SourceHint")
        self._hint.setText("Open a reference to compare…")

        self._toolbar = QWidget()
        toolbar_layout = QHBoxLayout(self._toolbar)
        toolbar_layout.setContentsMargins(10, 6, 10, 6)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addWidget(self._file_label)
        toolbar_layout.addWidget(self._file_model)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self._hint)
        # Everything mode-dependent starts hidden; ``refresh`` shows the
        # right set for the current mode.
        self._toolbar.setVisible(False)
        for control in (self._file_label, self._file_model, self._hint):
            control.setVisible(False)

        # Pane headers, one row shared by both panes. Each side leads with
        # its quiet role word, then the filename in the same defined
        # semibold as the single-pane strip (reference purple on the
        # reference side), then the model as a muted detail. Only the
        # names elide: the role words and models are short and fixed.
        self._main_role = QLabel("Main")
        self._main_role.setObjectName("SourcePaneRole")
        self._main_head = ElidedLabel("SourceFileName")
        self._main_model = QLabel()
        self._main_model.setObjectName("SourceFileModel")
        self._ref_role = QLabel("Reference")
        self._ref_role.setObjectName("SourcePaneRoleReference")
        self._ref_head = ElidedLabel("SourceReferenceName")
        self._ref_model = QLabel()
        self._ref_model.setObjectName("SourceFileModel")
        self._pane_head = QWidget()
        head_layout = QHBoxLayout(self._pane_head)
        head_layout.setContentsMargins(10, 2, 10, 2)
        main_side = QHBoxLayout()
        main_side.setContentsMargins(0, 0, 0, 0)
        main_side.setSpacing(6)
        main_side.addWidget(self._main_role)
        main_side.addWidget(self._main_head)
        main_side.addWidget(self._main_model)
        main_side.addStretch(1)
        head_layout.addLayout(main_side, 1)
        gutter_spacer = QWidget()
        gutter_spacer.setFixedWidth(_GUTTER_PX)
        head_layout.addWidget(gutter_spacer)
        # The reference pane's header carries a badge per pinned reference,
        # exactly one filled -- the same selector grammar the card's
        # reference grid uses, and the same identity language every other
        # comparison surface speaks. Rebuilt per refresh (pin order owns
        # it), so it lives in a slot rather than being a fixed child.
        self._ref_badge_slot = QHBoxLayout()
        self._ref_badge_slot.setContentsMargins(0, 0, 0, 0)
        self._ref_badge_slot.setSpacing(4)
        self._ref_badge_buttons: list[badges.ReferenceBadgeButton] = []
        ref_side = QHBoxLayout()
        ref_side.setContentsMargins(0, 0, 0, 0)
        ref_side.setSpacing(6)
        ref_side.addLayout(self._ref_badge_slot)
        ref_side.addWidget(self._ref_role)
        ref_side.addWidget(self._ref_head)
        ref_side.addWidget(self._ref_model)
        ref_side.addStretch(1)
        head_layout.addLayout(ref_side, 1)
        self._pane_head.setVisible(False)

        # Stale-reference band: a slim neutral notice directly under the
        # pane headers. Shown/hidden by MainWindow's on-notice mtime check
        # (page entry, window activation) -- no file watching, never a
        # silent refresh.
        self._stale_band = QWidget()
        self._stale_band.setObjectName("SourceStaleBand")
        stale_layout = QHBoxLayout(self._stale_band)
        stale_layout.setContentsMargins(12, 3, 12, 3)
        stale_layout.setSpacing(8)
        self._stale_text = QLabel()
        self._stale_text.setObjectName("SourceStaleText")
        self._stale_text.setWordWrap(True)
        stale_layout.addWidget(self._stale_text)
        self._reload_button = QPushButton("Reload")
        self._reload_button.setObjectName("SourceReloadLink")
        self._reload_button.setCursor(Qt.PointingHandCursor)
        self._reload_button.clicked.connect(self.reload_requested)
        stale_layout.addWidget(self._reload_button)
        stale_layout.addStretch(1)
        self._stale_band.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._pane_head)
        layout.addWidget(self._stale_band)
        layout.addWidget(self._view, 1)

    def refresh(
        self,
        main_raw: dict | None,
        pins=None,
        main_name: str = "",
        main_model: str | None = None,
        selected: int = 0,
        pull_enabled: bool = True,
    ) -> None:
        """Re-render from the current document and the pinned references.

        Called from ``MainWindow._apply_comparison`` -- the same fan-out
        every comparison-state change already goes through -- so edits,
        undo/redo, open/new and pin/remove all land here. With at least one
        reference pinned the page renders the aligned two-pane comparison;
        *main_name*/*main_model* label the main pane's header.

        The page shows **one** reference at a time -- two raw-JSON panes are
        already as much as the eye can align -- and *selected* says which.
        Its badge selector switches between them; with a single pin the
        selector is a lone badge, since a control with one choice is not a
        choice.
        """
        pins = list(pins or [])
        self._selected_reference = min(selected, len(pins) - 1) if pins else 0
        pin = pins[self._selected_reference] if pins else None
        reference = pin.snapshot if pin is not None else None
        two_pane = main_raw is not None and reference is not None
        single_pane = main_raw is not None and reference is None
        self._hint.setVisible(single_pane)
        self._file_label.setText(main_name if single_pane else "")
        self._file_label.setVisible(single_pane)
        self._file_model.setText((main_model or "") if single_pane else "")
        self._file_model.setVisible(single_pane and bool(main_model))
        # Texts land before the strip shows: a first layout pass against
        # the empty construction text would size the labels to nothing.
        self._toolbar.setVisible(single_pane)
        self._has_document = main_raw is not None
        self._update_fold_visible()
        if not two_pane:
            # The band is a two-pane notice; an undocked/replaced reference
            # takes it with it (a fresh dock re-checks from MainWindow).
            self._stale_band.setVisible(False)
        self._set_reference_badges(pins if two_pane else [])
        if two_pane:
            self._main_head.setText(main_name)
            self._main_model.setVisible(bool(main_model))
            self._main_model.setText(main_model or "")
            self._ref_head.setText(reference.filename)
            self._ref_model.setVisible(bool(reference.model))
            self._ref_model.setText(reference.model or "")
            # Origin on hover: the header names the reference; where it came
            # from (a bundled library set, or which file on disk) is the
            # transparency fact the pane otherwise never states. Set after
            # the name: ``ElidedLabel.setText`` resets the tooltip to its
            # own full text, and the origin must win.
            if reference.set_id is not None:
                self._ref_head.setToolTip("Reference library")
            elif reference.path is not None:
                self._ref_head.setToolTip(str(reference.path))
            else:
                self._ref_head.setToolTip("")
            rows = build_rows(main_raw, reference.raw)
        else:
            rows = build_rows(main_raw) if main_raw is not None else []
        # Shown only after its texts are set, for the same first-layout
        # reason as the single-pane strip above.
        self._pane_head.setVisible(two_pane)
        self._view.set_rows(rows, two_pane=two_pane, pull_enabled=pull_enabled)

    def selected_reference_index(self) -> int:
        """The pin index the reference pane is currently showing."""
        return self._selected_reference

    def _set_reference_badges(self, pins: list) -> None:
        """Rebuild the reference pane's selector, exactly one badge filled."""
        for button in self._ref_badge_buttons:
            self._ref_badge_slot.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        self._ref_badge_buttons = []
        for index, pin in enumerate(pins):
            button = badges.ReferenceBadgeButton(
                pin.letters, pin.colour, pin.name, checked=index == self._selected_reference
            )
            button.clicked.connect(self._on_reference_badge_clicked)
            self._ref_badge_buttons.append(button)
            self._ref_badge_slot.addWidget(button)

    def _on_reference_badge_clicked(self) -> None:
        """Exclusive selection. Re-emitted rather than handled here: which
        reference the page compares against is MainWindow's state, and the
        pane's rows, the stale band and the ← pull arrows all have to move
        together with it."""
        button = self.sender()
        if button not in self._ref_badge_buttons:
            return
        index = self._ref_badge_buttons.index(button)
        for position, other in enumerate(self._ref_badge_buttons):
            other.setChecked(position == index)
        if index != self._selected_reference:
            self.reference_selected.emit(index)

    def fold_button(self) -> QPushButton:
        """The fold-all toggle, for MainWindow to dock into the page-header
        bar's trailing slot -- the page builds and drives it (label, fold
        action, visibility) but never lays it out."""
        return self._fold_button

    def set_page_active(self, active: bool) -> None:
        """Tell the page whether it is the window's current page. The fold
        button renders only then: it sits in the bar every page shares, and
        must not outlive the page it acts on."""
        self._page_active = active
        self._update_fold_visible()

    def _update_fold_visible(self) -> None:
        self._fold_button.setVisible(self._has_document and self._page_active)

    def _on_fold_toggle(self) -> None:
        self._view.set_tables_folded(self._view.all_tables_expanded())

    def _update_fold_button(self) -> None:
        if self._view.all_tables_expanded():
            self._fold_button.setText("▾ Collapse Parameters")
        else:
            self._fold_button.setText("▸ Expand Parameters")

    def focus_view(self) -> None:
        """Give the raw-JSON view keyboard focus, so Up/Down row navigation
        works immediately on page entry without a click first."""
        self._view.setFocus()

    def flash_pulled(self, path: tuple[str, ...]) -> None:
        """Show the view's transient "Used" tag on *path*'s row (called
        by MainWindow after the pull command commits and the page has
        re-rendered)."""
        self._view.flash_pulled(path)

    def set_stale_names(self, names: list[str]) -> None:
        """Name the pinned references whose files changed on disk.

        Any pin can go stale, not just the one on screen, so the band names
        them rather than saying "the reference" and leaving the reader to
        guess which. An empty list hides the band.
        """
        if names:
            self._stale_text.setText(f"{', '.join(names)} changed on disk")
        self.set_stale(bool(names))

    def set_stale(self, stale: bool) -> None:
        """Show/hide the stale-reference band (MainWindow's on-notice mtime
        check owns the decision; the page only renders it). Meaningless
        without a docked reference -- ``refresh`` hides it with the panes."""
        self._stale_band.setVisible(stale and not self._pane_head.isHidden())
