"""Reading a CSV file into columns and auto-mapping them to target fields.

Pure and Qt-free, like :mod:`.paste`. This is the file-based sibling of the
clipboard parser, feeding the CSV import dialog for a Validation run: one file
usually carries all four experiment arrays (time, current, voltage,
temperature), so the result is column-major and each column can be routed to a
different parameter.

The app's conventions hold throughout:

* **Cells are raw objects, never coerced** -- numeric text becomes ``int`` /
  ``float`` via the shared lenient convention, anything else stays a verbatim
  string (counted in ``rejected``), a missing cell is ``None``. Nothing is
  zero-filled.
* **The header row is detected, never assumed** -- a first row whose cells are
  all non-numeric names the columns; without one, columns are just "Column N".
* **Auto-mapping is a suggestion, never a decision** -- :func:`auto_map` only
  proposes defaults for the mapping dialog, which the user always sees and can
  always override. A wrong guess is visible, not silently imported.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

from .paste import detect_delimiter
from .values import parse_value

_DELIMITER_NAMES = {",": "comma", ";": "semicolon", "\t": "tab"}


@dataclass(frozen=True)
class CsvData:
    """A CSV file's content, column-major, lenient-parsed."""

    #: Header names from a detected header row, or ``None`` when the file has
    #: no header (columns are then addressed positionally).
    headers: tuple[str, ...] | None
    #: One tuple per column. Columns are equal length: a short row's missing
    #: trailing cells are ``None`` (honest "no value"), never invented.
    columns: tuple[tuple[object, ...], ...]
    delimiter: str
    #: How many cells did not parse as numbers (kept as verbatim text).
    rejected: int

    @property
    def column_count(self) -> int:
        """How many columns the file yielded."""
        return len(self.columns)

    @property
    def row_count(self) -> int:
        """How many data rows the file yielded (all columns are equal length)."""
        return len(self.columns[0]) if self.columns else 0

    def column_name(self, index: int) -> str:
        """A display name for column *index*: its header, or "Column N"."""
        if self.headers is not None and self.headers[index]:
            return self.headers[index]
        return f"Column {index + 1}"


def read_csv_file(path: str) -> CsvData:
    """Read *path* BOM-tolerantly and parse it like :func:`read_csv_text`.

    Shared by both import surfaces (the series card and the grid's own
    ``import_csv``) so the file-reading convention -- a byte that is not
    UTF-8 survives as a visible replacement character rather than aborting
    the import -- lives in one place.
    """
    with Path(path).open(encoding="utf-8-sig", errors="replace") as handle:
        return read_csv_text(handle.read())


def read_csv_text(text: str) -> CsvData:
    """Parse CSV *text* into :class:`CsvData`.

    Quoted fields are honoured via :mod:`csv` when the delimiter can be
    sniffed; a file the sniffer cannot classify (e.g. whitespace-aligned
    columns) falls back to the clipboard parser's delimiter detection, so a
    ``.txt`` export still imports.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return CsvData(None, (), "single column", 0)

    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",;\t")
        raw_rows = [row for row in csv.reader(io.StringIO(text), dialect) if _has_content(row)]
        delimiter = _DELIMITER_NAMES.get(dialect.delimiter, "comma")
    except csv.Error:
        delimiter = detect_delimiter(text)
        raw_rows = [_fallback_split(line, delimiter) for line in lines]

    headers: tuple[str, ...] | None = None
    if len(raw_rows) > 1 and _is_header_row(raw_rows[0]):
        headers = tuple(cell.strip() for cell in raw_rows[0])
        raw_rows = raw_rows[1:]

    width = max((len(row) for row in raw_rows), default=0)
    if headers is not None and len(headers) < width:
        headers = headers + ("",) * (width - len(headers))

    rejected = 0
    grid: list[list[object]] = []
    for row in raw_rows:
        cells: list[object] = []
        for index in range(width):
            value = parse_value(row[index]) if index < len(row) else None
            if value is not None and not isinstance(value, (int, float)):
                rejected += 1
            cells.append(value)
        grid.append(cells)

    columns = tuple(tuple(row[i] for row in grid) for i in range(width))
    return CsvData(headers, columns, delimiter, rejected)


def auto_map(data: CsvData, targets: tuple[str, ...]) -> tuple[int | None, ...]:
    """Propose a file column for each target field, or ``None`` for no guess.

    With headers, columns are matched by normalised name (units and
    punctuation stripped): "time (s)" finds "Time [s]", "Temp" finds
    "Temperature [K]". Each column is proposed at most once. Without headers,
    the proposal is positional (:func:`positional_map`) -- exactly what an
    export of the four arrays in order looks like. Either way the mapping
    dialog shows the result for the user to correct.
    """
    if data.headers is None:
        return positional_map(data.column_count, len(targets))

    normalised = [_normalise(header) for header in data.headers]
    used: set[int] = set()
    mapping: list[int | None] = []
    for target in targets:
        key = _normalise(target)
        match: int | None = None
        for index, header in enumerate(normalised):
            if index in used or not header or not key:
                continue
            if header == key or key in header or header in key:
                match = index
                break
        if match is not None:
            used.add(match)
        mapping.append(match)
    return tuple(mapping)


def positional_map(width: int, count: int) -> tuple[int | None, ...]:
    """Propose file column N for target N, with ``None`` past the file's *width*.

    This is :func:`auto_map`'s own no-header branch, lifted out so a caller
    with short, generic target names -- an x/y table's "x" and "y" -- can use
    it directly. ``auto_map``'s header-matching rule (``key in header or
    header in key``) is a reasonable heuristic for a distinctive name like
    "Temperature [K]", but for a single letter it is dangerous: "x" would
    happily match a header like "Extraction", "y" would match "Capacity".
    Positional order is the safe, honest guess for such targets; the mapping
    dialog still shows it for the user to correct.

    Takes the file's column count as a plain ``int`` (not a whole
    :class:`CsvData`) -- it reads exactly one integer, so it is a pure
    function of two numbers.
    """
    return tuple(index if index < width else None for index in range(count))


def _normalise(name: str) -> str:
    """Lowercased letters/digits with any bracketed unit removed.

    "Time [s]" -> "time", "time (s)" -> "time", "Temp." -> "temp".
    """
    without_units = re.sub(r"[\[(].*?[\])]", " ", name)
    return re.sub(r"[^a-z0-9]", "", without_units.lower())


def _has_content(row: list[str]) -> bool:
    return any(cell.strip() for cell in row)


def _is_header_row(row: list[str]) -> bool:
    """A row is a header when it has cells and none of them is a number."""
    cells = [cell for cell in row if cell.strip()]
    if not cells:
        return False
    return all(not isinstance(parse_value(cell), (int, float)) for cell in cells)


def _fallback_split(line: str, delimiter: str) -> list[str]:
    if delimiter in ("whitespace", "single column"):
        return line.split()
    for char, name in _DELIMITER_NAMES.items():
        if name == delimiter:
            return [token.strip() for token in line.split(char)]
    return [line.strip()]
