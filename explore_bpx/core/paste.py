"""Parsing pasted tabular text into grid rows (pure, Qt-free, testable).

A user pasting a column of numbers from a spreadsheet, or an ``x,y`` table from
a CSV, should land in the grid without hand-retyping. This module turns raw
clipboard text into rows of cell objects, honouring the same conventions the
rest of the app does:

* **Cells are raw objects, never coerced.** A token that parses as a number
  becomes an ``int``/``float`` (:func:`~.values.parse_value`); anything else is
  kept as its verbatim string. A cell is *never* zero-filled -- a value that
  does not parse is reported to the user, not silently replaced.
* **The delimiter is detected, not assumed** (tab, comma, semicolon, or runs of
  whitespace), so a paste from Excel, a CSV, or a whitespace-aligned table all
  work.
* **A non-numeric header row is skipped**, and reported, so pasting a block that
  begins ``time,voltage`` does not inject that line as data.

The parser knows the target grid's column count and shapes every row to it:
extra columns are dropped (reported), missing ones are blank (``None``). The
preview built from :class:`ParsedPaste` is what the user confirms before
anything touches the document.
"""

from __future__ import annotations

from dataclasses import dataclass

from .values import parse_value

#: Candidate delimiters, tried in order of specificity. Whitespace is the
#: fallback: a run of spaces/tabs, matched by ``str.split()`` with no argument.
_DELIMITERS: tuple[tuple[str, str], ...] = (
    ("tab", "\t"),
    ("comma", ","),
    ("semicolon", ";"),
)


@dataclass(frozen=True)
class ParsedPaste:
    """The outcome of parsing pasted text against a target column count."""

    rows: list[list[object]]
    #: Human-readable delimiter name: ``tab`` / ``comma`` / ``semicolon`` /
    #: ``whitespace`` (or ``single column`` when the text has one column).
    delimiter: str
    #: The header line that was skipped, verbatim, or ``None`` if none was.
    header: str | None
    #: How many cells did not parse as numbers (kept as text, not dropped).
    rejected: int
    #: How many source columns exceeded the target width and were dropped.
    dropped_columns: int

    @property
    def row_count(self) -> int:
        """How many rows the pasted block yielded."""
        return len(self.rows)


def detect_delimiter(text: str) -> str:
    """Return the delimiter name best fitting *text*'s first data line.

    Picks the most specific delimiter that actually appears; falls back to
    whitespace when none do. A single unbroken token yields ``single column``.
    """
    line = _first_nonblank(text)
    if line is None:
        return "single column"
    for name, char in _DELIMITERS:
        if char in line:
            return name
    if len(line.split()) > 1:
        return "whitespace"
    return "single column"


def parse_clipboard(text: str, columns: int) -> ParsedPaste:
    """Parse pasted *text* into rows of *columns* cell objects.

    A leading all-non-numeric line is treated as a header and skipped. Each
    remaining line is split on the detected delimiter; tokens are parsed with
    the app's lenient convention; the row is shaped to exactly *columns* cells
    (extra tokens dropped and counted, missing ones left blank).
    """
    lines = [line for line in text.splitlines() if line.strip()]
    delimiter = detect_delimiter(text)
    if not lines:
        return ParsedPaste([], delimiter, None, 0, 0)

    header: str | None = None
    if len(lines) > 1 and _is_header(lines[0], delimiter):
        header = lines[0]
        lines = lines[1:]

    rows: list[list[object]] = []
    rejected = 0
    dropped_columns = 0
    for line in lines:
        tokens = _split(line, delimiter)
        if len(tokens) > columns:
            dropped_columns += len(tokens) - columns
        cells: list[object] = []
        for index in range(columns):
            token = tokens[index] if index < len(tokens) else ""
            value = parse_value(token)
            if value is not None and not isinstance(value, (int, float)):
                rejected += 1
            cells.append(value)
        rows.append(cells)
    return ParsedPaste(rows, delimiter, header, rejected, dropped_columns)


def _split(line: str, delimiter: str) -> list[str]:
    if delimiter in {"whitespace", "single column"}:
        return line.split()
    char = dict(_DELIMITERS)[delimiter]
    return [token.strip() for token in line.split(char)]


def _is_header(line: str, delimiter: str) -> bool:
    """A line is a header when it has tokens and none of them is a number."""
    tokens = _split(line, delimiter)
    if not tokens:
        return False
    return all(not isinstance(parse_value(token), (int, float)) and parse_value(token) is not None for token in tokens)


def _first_nonblank(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line
    return None
