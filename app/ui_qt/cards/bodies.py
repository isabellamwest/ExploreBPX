"""Mode bodies: one editor per legal representation of a union-typed field.

A body is *not* an :class:`~.base.EditorCard`. It edits one representation and
knows nothing about drafts, dirtiness, commits or the document. The
:class:`~.modal.ModalCard` that owns a strip of bodies supplies all of that.

Each body implements the small protocol in :mod:`~.modal`:

    ``value()``  ``set_value(v)``  ``reset()``  ``focus_widget()``  ``changed``

Bodies keep their own draft. Switching mode swaps which body is visible; it
never seeds, clears or copies between them (see decision C in the plan:
switching mode *completely changes* the value, so ``3.7`` → ``InterpolatedTable``
gives an empty grid, not a one-row table).

``RawJsonBody`` is the one editor that gates on **syntax**. Every other card in
the app emits raw input and lets the validator judge legality; a Raw body
holding unparseable text has no value to emit *at all*, and committing its text
as a string would replace a table with a broken string. That is data loss, not
an invalid edit -- so it reports a ``commit_blocked_reason``.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import bpx_gateway
from core.values import format_value, parse_value

from ..style import ERROR, MUTED, VALUE_INPUT_MAX_WIDTH
from .cell_issues import table_cells
from .grid import NumericGrid
from .hint import GridHint
from .table_preview import TablePreview


class ModeBody(QWidget):
    """Base class for a single representation's editor."""

    changed = Signal()
    #: Forwarded up to the card when a grid body asks to expand. A body with no
    #: grid (numbers, expressions, JSON) never emits it.
    expand_toggled = Signal(bool)

    def value(self) -> object:
        """The body's current draft, in raw-dict form."""
        raise NotImplementedError

    def set_value(self, value: object) -> None:
        """Seed the body from a committed value (never called on mode switch)."""
        raise NotImplementedError

    def reset(self) -> None:
        """Restore whatever :meth:`set_value` last seeded, or empty."""
        raise NotImplementedError

    def focus_widget(self) -> QWidget:
        """The widget that takes keyboard focus, for the card's key handler."""
        raise NotImplementedError

    def commit_blocked_reason(self) -> str | None:
        """Why this body's draft has no representation, or ``None``."""
        return None

    def set_cell_issues(self, issues) -> None:
        """Render the validator's per-cell diagnostics, if this body has cells.

        A no-op for most bodies. ``ModalCard`` only ever calls this on the
        *active* body, so a body currently hidden never needs to answer.
        """

    @property
    def accepts_multiline_input(self) -> bool:
        """True when Shift+Enter should insert a newline rather than commit."""
        return False

    def insert_newline(self) -> None:  # pragma: no cover - only multiline bodies
        raise NotImplementedError


class NumberBody(ModeBody):
    """``FloatInt``: a free-text number field plus the parameter's unit.

    *unit_tooltip*, when given, is set on the unit label -- the caller's job
    (``FunctionCard``/``MapCard``) to decide, from
    ``core.structure.can_rename_parameter`` on the parameter's own path and
    value, since this body knows only the unit string, never the path.
    """

    def __init__(self, unit: str = "", unit_tooltip: str = "") -> None:
        super().__init__()
        self._seed: object = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit()
        self._edit.setMaximumWidth(VALUE_INPUT_MAX_WIDTH)
        self._edit.textChanged.connect(lambda *_: self.changed.emit())
        layout.addWidget(self._edit, 1)
        #: The unit label, or ``None`` when no unit was given -- kept as an
        #: attribute (not just laid out) so tests can read its tooltip.
        self._unit_label: QLabel | None = None
        if unit:
            self._unit_label = QLabel(unit)
            self._unit_label.setObjectName("UnitLabel")
            if unit_tooltip:
                self._unit_label.setToolTip(unit_tooltip)
            layout.addWidget(self._unit_label)
        layout.addStretch(1)

    def value(self) -> object:
        return parse_value(self._edit.text())

    def set_value(self, value: object) -> None:
        self._seed = value
        self._edit.setText(format_value(value))

    def reset(self) -> None:
        self._edit.setText(format_value(self._seed))

    def focus_widget(self) -> QWidget:
        return self._edit


class ExpressionBody(ModeBody):
    """``Function``: a free-text expression, hinted by ``bpx.Function``'s own docs."""

    def __init__(self) -> None:
        super().__init__()
        self._seed: object = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText("e.g. 2*x + exp(-x)")
        self._edit.textChanged.connect(lambda *_: self.changed.emit())
        layout.addWidget(self._edit)

        # Quoted from the package so the hint tracks what bpx actually accepts.
        hint = QLabel(bpx_gateway.function_syntax_help())
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(hint)

    def value(self) -> object:
        """The expression verbatim -- but a bare number is still a number.

        A ``Function`` field accepts a numeric constant, and the app's lenient
        convention means typing ``3.7`` here commits the float, so the value
        reclassifies to its numeric mode on the next rebuild rather than
        becoming the string ``"3.7"``.
        """
        return parse_value(self._edit.text())

    def set_value(self, value: object) -> None:
        self._seed = value
        self._edit.setText(format_value(value))

    def reset(self) -> None:
        self._edit.setText(format_value(self._seed))

    def focus_widget(self) -> QWidget:
        return self._edit


class TableBody(ModeBody):
    """``InterpolatedTable``: a two-column ``x``/``y`` grid over a live preview.

    The plotted line is the value: an interpolated table *is* the piecewise-
    linear function through its points, so the preview shows exactly what the
    grid defines.
    """

    def __init__(self) -> None:
        super().__init__()
        self._seed: object = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._preview = TablePreview(mode="xy")
        self._preview.set_axis_titles("x", "y")
        layout.addWidget(self._preview)

        self._grid = NumericGrid(("x", "y"), csv_import=True)
        self._grid.changed.connect(self._on_grid_changed)
        self._grid.expand_toggled.connect(self.expand_toggled)
        layout.addWidget(self._grid, 1)

        layout.addWidget(
            GridHint(
                (
                    "Each row is one (x, y) point; the line above plots them in order.",
                    "Double-click a cell to edit; press Enter to commit, Esc to discard.",
                    "Paste two columns from a spreadsheet with Ctrl+V, or right-click → Paste.",
                    "Use + and − to add or remove points; Expand fills the panel.",
                    "Import CSV… loads x and y from the columns of a file.",
                )
            )
        )

    def _on_grid_changed(self) -> None:
        self._preview.update_rows(self._grid.values())
        self.changed.emit()

    def set_cell_issues(self, issues) -> None:
        self._grid.set_cell_issues(table_cells(issues))

    def value(self) -> object:
        """``{"x": [...], "y": [...]}``, cells verbatim. An empty grid is empty lists."""
        rows = self._grid.values()
        return {"x": [row[0] for row in rows], "y": [row[1] for row in rows]}

    def set_value(self, value: object) -> None:
        self._seed = value
        self._grid.set_values(_table_rows(value))
        self._preview.update_rows(self._grid.values())

    def reset(self) -> None:
        self._grid.set_values(_table_rows(self._seed))
        self._preview.update_rows(self._grid.values())

    def focus_widget(self) -> QWidget:
        return self._grid.focus_widget()


class MaterialMapBody(ModeBody):
    """``dict[str, FloatInt]``: a per-material map of key -> scalar.

    Each row is a material name (a sibling ``Particle`` key, e.g. ``Primary``)
    and its value. Keys are free text: an unknown key is allowed and committed,
    because the BPX validator -- not this editor -- decides which particle names
    are legal (the row simply offers the known names as suggestions).

    Two rows cannot share a key: a dict would keep only one, silently dropping
    the other. That is data loss, not an invalid value, so a duplicate key
    blocks the commit and is explained inline -- the same principle as
    :class:`RawJsonBody`'s syntax gate.
    """

    def __init__(self, suggestions: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._seed: object = None
        self._suggestions = tuple(suggestions)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._grid = NumericGrid(
            ("Material", "Value"), text_columns=frozenset({0}), bulk=False
        )
        self._grid.changed.connect(self._on_changed)
        layout.addWidget(self._grid)

        # The known particle names, offered but never enforced. Absent on a
        # single-particle electrode, where the dict mode is still reachable
        # (decision F) but has no names to suggest -- the plain "+" row is then
        # the only way to add one, which is exactly right.
        if self._suggestions:
            self._menu = QMenu(self)
            self._menu.aboutToShow.connect(self._populate_menu)
            button = QToolButton()
            button.setObjectName("AddMaterialButton")
            button.setText("Material")
            button.setToolTip("Add a known material")
            button.setAccessibleName("Add material")
            button.setAutoRaise(True)
            button.setPopupMode(QToolButton.InstantPopup)
            button.setMenu(self._menu)
            self._grid.add_toolbar_widget(button)

        self._error = QLabel()
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {ERROR};")
        self._error.hide()
        layout.addWidget(self._error)

    def _on_changed(self) -> None:
        self._refresh_error()
        self.changed.emit()

    def _refresh_error(self) -> None:
        reason = self.commit_blocked_reason()
        self._error.setText(reason or "")
        self._error.setVisible(reason is not None)

    def _populate_menu(self) -> None:
        """Offer only the suggestions not already used, resolved each open."""
        self._menu.clear()
        used = {key for key, _ in self._rows()}
        remaining = [name for name in self._suggestions if name not in used]
        if not remaining:
            action = self._menu.addAction("All materials added")
            action.setEnabled(False)
            return
        for name in remaining:
            self._menu.addAction(name, lambda checked=False, n=name: self._add_material(n))

    def _add_material(self, name: str) -> None:
        self._grid.append_row([name, None])

    def _rows(self) -> list[tuple[str, object]]:
        """The keyed rows: (key, value) for every row whose key is non-empty.

        A blank-keyed row (a freshly added ``+`` row, or a value typed before
        its name) is not yet a dict entry and is skipped -- a dict entry needs a
        key, and inventing ``""`` for it would fabricate a value nobody typed.
        """
        rows: list[tuple[str, object]] = []
        for key, value in self._grid.values():
            if key is None:
                continue
            rows.append((str(key), value))
        return rows

    def value(self) -> object:
        """The map as a dict. On a duplicate key the later row wins, but such a
        draft is blocked from commit (:meth:`commit_blocked_reason`)."""
        return {key: value for key, value in self._rows()}

    def commit_blocked_reason(self) -> str | None:
        seen: set[str] = set()
        for key, _ in self._rows():
            if key in seen:
                return (
                    f'Duplicate material "{key}" - each material may appear '
                    "only once."
                )
            seen.add(key)
        return None

    def set_value(self, value: object) -> None:
        self._seed = value
        self._grid.set_values(_map_rows(value))
        self._refresh_error()

    def reset(self) -> None:
        self._grid.set_values(_map_rows(self._seed))
        self._refresh_error()

    def focus_widget(self) -> QWidget:
        return self._grid.focus_widget()


class RawJsonBody(ModeBody):
    """``Raw``: the stored value as JSON text, for values no mode can represent.

    The only editor in the app that refuses a draft. Unparseable text has no
    value to commit; committing it as a string would destroy the stored
    structure. The parse error is shown inline as the user types.
    """

    def __init__(self, notice: str = "") -> None:
        super().__init__()
        self._seed: object = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        if notice:
            label = QLabel(notice)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {MUTED};")
            layout.addWidget(label)

        self._edit = QPlainTextEdit()
        self._edit.setTabChangesFocus(True)
        self._edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit)

        self._error = QLabel()
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {ERROR};")
        self._error.hide()
        layout.addWidget(self._error)

    def _on_text_changed(self) -> None:
        self._refresh_error()
        self.changed.emit()

    def _refresh_error(self) -> None:
        reason = self.commit_blocked_reason()
        self._error.setText(reason or "")
        self._error.setVisible(reason is not None)

    def commit_blocked_reason(self) -> str | None:
        text = self._edit.toPlainText().strip()
        if not text:
            return None  # empty means null, which is a real (if invalid) value
        try:
            json.loads(text)
        except ValueError as exc:
            return f"Not valid JSON: {exc}"
        return None

    def value(self) -> object:
        """The parsed JSON, or the seeded value while the text does not parse.

        Falling back to the seed rather than inventing a value is the last line
        of defence: even if a caller ignored ``commit_blocked_reason``, the
        worst it could write is the value already stored.

        A consequence worth knowing: because the seed *is* the committed value,
        a blocked draft always compares equal to the original, so ``is_dirty``
        is False and the Inspector's dirty check would refuse the commit even
        without the block. The block is what makes the refusal *deliberate*, and
        it becomes decisive for a body whose blocked draft genuinely differs
        from the original (duplicate map keys).
        """
        text = self._edit.toPlainText().strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return self._seed

    def set_value(self, value: object) -> None:
        self._seed = value
        self._edit.setPlainText(_to_json(value))
        self._refresh_error()

    def reset(self) -> None:
        self._edit.setPlainText(_to_json(self._seed))
        self._refresh_error()

    def focus_widget(self) -> QWidget:
        return self._edit

    @property
    def accepts_multiline_input(self) -> bool:
        return True

    def insert_newline(self) -> None:
        self._edit.insertPlainText("\n")


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _to_json(value: object) -> str:
    """Pretty JSON for display; a value JSON cannot express falls back to text."""
    if value is None:
        return ""
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except TypeError:  # pragma: no cover - defensive
        return str(value)


def _map_rows(value: object) -> list[list[object]]:
    """Zip a ``{key: value}`` map into ``[key, value]`` grid rows.

    Only ever called with a value the card judged representable (a dict of
    scalar-shaped values), or with ``None``/anything else for an unseeded body,
    which yields an empty grid. Insertion order is preserved so the editor shows
    materials in the order they were stored.
    """
    if not isinstance(value, dict):
        return []
    return [[key, item] for key, item in value.items()]


def _table_rows(value: object) -> list[list[object]]:
    """Zip a ``{"x": [...], "y": [...]}`` dict into grid rows.

    Only ever called with a value the registry judged representable, or with
    ``None``/anything else for an unseeded body, which yields an empty grid.
    """
    if not isinstance(value, dict):
        return []
    xs, ys = value.get("x"), value.get("y")
    if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != len(ys):
        return []
    return [[x, y] for x, y in zip(xs, ys)]
