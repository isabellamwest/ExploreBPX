"""Mode bodies: one editor per legal representation of a union-typed field.

A body is *not* an :class:`~.base.EditorCard`. It edits one representation and
knows nothing about drafts, dirtiness, commits or the document. The
:class:`~.modal.ModalCard` that owns a strip of bodies supplies all of that.

Each body implements the small protocol in :mod:`~.modal`:

    ``value()``  ``set_value(v)``  ``reset()``  ``focus_widget()``  ``changed``

Bodies keep their own draft. Switching mode swaps which body is visible; it
never seeds, clears or copies between them: switching mode *completely
changes* the value, so ``3.7`` → ``InterpolatedTable`` gives an empty grid,
not a one-row table.

``RawJsonBody`` is the one editor that gates on **syntax**. Every other card in
the app emits raw input and lets the validator judge legality; a Raw body
holding unparseable text has no value to emit *at all*, and committing its text
as a string would replace a table with a broken string. That is data loss, not
an invalid edit -- so it reports a ``commit_blocked_reason``.
"""

from __future__ import annotations

import json
import math

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
from ui_qt import typography
from ui_qt.style import ACCENT, ERROR, MUTED, VALUE_INPUT_MAX_WIDTH

from .cell_issues import table_cells
from .grid import NumericGrid
from .hint import GridHint, WrappedHelp
from .multi_series_chart import MultiSeriesChart
from .table_preview import TablePreview


class ModeBody(QWidget):
    """Base class for a single representation's editor."""

    changed = Signal()

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

    def pending_grid(self):
        """This body's grid, for the card to drive its "Unsaved changes" bar
        (``EditorCard._bind_grid_pending``) -- ``None`` for a body without
        one (numbers, expressions, JSON)."""
        return

    def reference_value_width(self) -> int | None:
        """See :meth:`~.base.EditorCard.reference_value_width`: the width cap
        of this body's input, or ``None`` for a full-width body."""
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
        # Zero-stretch: see ScalarCard -- deterministic input width, so the
        # reference row's box can match it exactly.
        layout.addStretch(0)

    def value(self) -> object:
        return parse_value(self._edit.text())

    def set_value(self, value: object) -> None:
        self._seed = value
        self._edit.setText(format_value(value))

    def reset(self) -> None:
        self._edit.setText(format_value(self._seed))

    def focus_widget(self) -> QWidget:
        return self._edit

    def reference_value_width(self) -> int | None:
        return VALUE_INPUT_MAX_WIDTH


#: Width of the preview-domain bound fields -- room for a full
#: scientific-notation bound (e.g. "-1.5e-06").
_DOMAIN_FIELD_WIDTH = 100


class ExpressionBody(ModeBody):
    """``Function``: a free-text expression, hinted by ``bpx.Function``'s own
    docs, over a chart previewing what it draws.

    The chart is evaluated by ``bpx`` itself
    (``core.bpx_gateway.sample_function``, itself ``bpx.Function.validate``
    then ``to_python_function``) -- this body never interprets the
    expression. It reflects only the *committed* value: populated by
    :meth:`set_value`/:meth:`reset`, never resampled per keystroke (see
    :meth:`_show`). The x domain it samples over is a compact, view-only
    pair of fields the user can widen or narrow (:attr:`_domain_low`/
    :attr:`_domain_high`) -- never written to the document, and never
    remembered between cards, so a freshly built body always reopens at the
    default ``[0, 1]``.

    *unit*, when given, names the chart's y axis (``"y [V]"``) -- the same
    unit ``TableBody``'s own preview shows for this parameter.
    """

    #: The preview domain's default extent (see the class docstring).
    _DEFAULT_LOW = 0.0
    _DEFAULT_HIGH = 1.0

    def __init__(self, unit: str = "") -> None:
        super().__init__()
        self._seed: object = None
        #: The committed value, only when it is itself a function-expression
        #: string -- ``None`` while unseeded (this was not the mode the
        #: committed value opened in) or last seeded with a bare number.
        #: What :meth:`_resample_main` samples.
        self._committed_expression: str | None = None
        self._domain_low = self._DEFAULT_LOW
        self._domain_high = self._DEFAULT_HIGH
        #: ``(ReferencePin, expression)`` per pinned reference whose value at
        #: this key is itself a function string -- see
        #: :meth:`set_reference_functions`.
        self._reference_functions: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Chart sits where TableBody's own preview sits: above the editor.
        self._chart = MultiSeriesChart(height=140)
        self._chart.set_axis_titles("x", f"y [{unit}]" if unit else "y")
        self._chart.set_empty_text("No expression to preview yet.")
        layout.addWidget(self._chart)

        # Occupies the chart's own place when the expression fails to
        # evaluate -- never shown alongside it (see _set_preview_error).
        self._error_note = WrappedHelp("")
        self._error_note.setStyleSheet(f"color: {MUTED}; {typography.size_qss(typography.META)}")
        self._error_note.hide()
        layout.addWidget(self._error_note)

        domain_row = QHBoxLayout()
        domain_row.setContentsMargins(0, 0, 0, 0)
        domain_row.addStretch(1)
        domain_row.addWidget(_domain_label("Preview domain"))
        self._domain_low_edit = QLineEdit(_format_domain_bound(self._domain_low))
        self._domain_low_edit.setObjectName("ExpressionDomainLow")
        self._domain_low_edit.setMaximumWidth(_DOMAIN_FIELD_WIDTH)
        domain_row.addWidget(self._domain_low_edit)
        domain_row.addWidget(_domain_label("to"))
        self._domain_high_edit = QLineEdit(_format_domain_bound(self._domain_high))
        self._domain_high_edit.setObjectName("ExpressionDomainHigh")
        self._domain_high_edit.setMaximumWidth(_DOMAIN_FIELD_WIDTH)
        domain_row.addWidget(self._domain_high_edit)
        # editingFinished (not textChanged): fires on Enter or focus-out,
        # never per keystroke, and this is view state -- never wired to
        # self.changed, so adjusting it can never dirty the card.
        self._domain_low_edit.editingFinished.connect(self._on_domain_edited)
        self._domain_high_edit.editingFinished.connect(self._on_domain_edited)
        layout.addLayout(domain_row)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("e.g. 2*x + exp(-x)")
        self._edit.textChanged.connect(lambda *_: self.changed.emit())
        layout.addWidget(self._edit)

        # Quoted from the package so the hint tracks what bpx actually
        # accepts -- only mechanically collapsed onto one muted line (the
        # multi-line docstring read as a slab of raw text under the input);
        # the words stay bpx's own.
        lines = bpx_gateway.function_syntax_help().splitlines()
        hint = WrappedHelp(" · ".join(line.strip().lstrip("- ") for line in lines if line.strip()))
        hint.setStyleSheet(f"color: {MUTED}; {typography.size_qss(typography.META)}")
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
        self._show(value)

    def reset(self) -> None:
        self._show(self._seed)

    def _show(self, value: object) -> None:
        """Populate the box reading from the *start* of the expression, and
        resample the chart from this same committed *value*.

        ``setText`` leaves the cursor at the end, which scrolls a long OCP
        expression so that the only part on screen is its tail -- the
        modeller cannot see what their own function begins with. Homing the
        cursor shows the beginning; the rest is one keystroke away either
        way, and nothing about the stored value changes.
        """
        self._edit.setText(format_value(value))
        self._edit.setCursorPosition(0)
        self._committed_expression = value if isinstance(value, str) else None
        self._resample_main()

    def focus_widget(self) -> QWidget:
        return self._edit

    # ------------------------------------------------------------------
    # Chart preview -- the committed value only, never a live keystroke
    # ------------------------------------------------------------------

    def set_reference_functions(self, entries) -> None:
        """Overlay one sampled curve per pinned reference whose value at
        this key is itself a function-expression string; an empty list
        clears every overlay.

        *entries* is ``(ReferencePin, expression)`` pairs, in pin order --
        ``ParameterCard``'s job to pick out the function-shaped references
        and pair them, this body never inspects a reference's value itself.
        Resampled here and again on every domain change
        (:meth:`_on_domain_edited`), independent of the main curve.
        """
        for pin, _expression in self._reference_functions:
            self._chart.remove_series(_reference_series_id(pin))
        self._reference_functions = list(entries)
        self._resample_references()

    def _resample_main(self) -> None:
        if self._committed_expression is None:
            self._chart.remove_series("main")
            self._set_preview_error(None)
            return
        samples = bpx_gateway.sample_function(self._committed_expression, self._domain_low, self._domain_high)
        if samples.error is not None:
            self._chart.remove_series("main")
            self._set_preview_error(samples.error)
            return
        self._set_preview_error(None)
        self._chart.set_series("main", list(samples.points), ACCENT, width=2.0, name="Main")

    def _resample_references(self) -> None:
        for pin, expression in self._reference_functions:
            series_id = _reference_series_id(pin)
            samples = bpx_gateway.sample_function(expression, self._domain_low, self._domain_high)
            if samples.error is not None:
                self._chart.remove_series(series_id)
                continue
            self._chart.set_series(series_id, list(samples.points), pin.colour, width=1.6, name=pin.name)

    def _set_preview_error(self, error: str | None) -> None:
        """Show the chart, or replace it with one muted note -- never both.

        The note is bpx's own message verbatim; this body invents nothing
        about *why* an expression failed, only whether to show the curve.
        """
        self._error_note.setText(error or "")
        self._error_note.setVisible(error is not None)
        self._chart.setVisible(error is None and self._chart.available)

    def _on_domain_edited(self) -> None:
        """``editingFinished`` on either domain field: parse both, revert
        both to the last good values on anything invalid (no dialog), or
        adopt the new domain and resample the main curve and every
        reference overlay.
        """
        try:
            low = float(self._domain_low_edit.text())
            high = float(self._domain_high_edit.text())
        except ValueError:
            low = high = math.nan
        if not math.isfinite(low) or not math.isfinite(high) or low >= high:
            self._domain_low_edit.setText(_format_domain_bound(self._domain_low))
            self._domain_high_edit.setText(_format_domain_bound(self._domain_high))
            return
        self._domain_low, self._domain_high = low, high
        self._resample_main()
        self._resample_references()


class TableBody(ModeBody):
    """``InterpolatedTable``: a two-column ``x``/``y`` grid over a live preview.

    The plotted line is the value: an interpolated table *is* the piecewise-
    linear function through its points, so the preview shows exactly what the
    grid defines.

    *unit*, when given, names the y axis (``"y [V]"``) -- the same unit
    ``NumberBody``'s own unit label shows for this parameter. ``x`` stays the
    bare letter: the spec gives an InterpolatedTable's x column no meaning of
    its own, so naming it would invent one.
    """

    def __init__(self, unit: str = "") -> None:
        super().__init__()
        self._seed: object = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._preview = TablePreview(mode="xy")
        self._preview.set_axis_titles("x", f"y [{unit}]" if unit else "y")
        layout.addWidget(self._preview)

        self._grid = NumericGrid(("x", "y"), csv_import=True)
        self._grid.changed.connect(self._on_grid_changed)
        layout.addWidget(self._grid, 1)

        layout.addWidget(
            GridHint(
                (
                    "Each row is one (x, y) point; the line above plots them in order.",
                    "Click a cell and type, or double-click, to edit it; Enter confirms the cell and moves down.",
                    "Your edits stay a draft until applied: Enter on the grid (or Apply) writes them to the file, "
                    "Esc (or Discard) reverts.",
                    "Paste two columns from a spreadsheet with Ctrl+V, or right-click → Paste.",
                    "Use + and − to add or remove points; the table grows to fill the panel.",
                    "Import CSV… loads x and y from the columns of a file.",
                )
            )
        )

    def _on_grid_changed(self) -> None:
        self._preview.update_rows(self._grid.values())
        self.changed.emit()

    def set_cell_issues(self, issues) -> None:
        self._grid.set_cell_issues(table_cells(issues))

    def set_reference_curves(self, curves) -> None:
        """Overlay one curve per pinned reference that has this key on the
        live preview; an empty list clears it. Each curve already carries
        the ``(x, y)`` pairs that reference's own grid would show (see
        :func:`table_rows`) -- this never re-parses a reference value
        itself. A no-op while this body is not the active mode: the card
        still calls it (see ``FunctionCard``/``TableCard``), it simply has
        nothing visible to show until the strip switches back here."""
        self._preview.set_reference_curves(curves)

    def pending_grid(self):
        return self._grid

    def value(self) -> object:
        """``{"x": [...], "y": [...]}``, cells verbatim. An empty grid is empty lists."""
        rows = self._grid.values()
        return {"x": [row[0] for row in rows], "y": [row[1] for row in rows]}

    def set_value(self, value: object) -> None:
        self._seed = value
        self._grid.set_values(table_rows(value))
        self._preview.update_rows(self._grid.values())

    def reset(self) -> None:
        self._grid.set_values(table_rows(self._seed))
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

        self._grid = NumericGrid(("Material", "Value"), text_columns=frozenset({0}), bulk=False)
        self._grid.changed.connect(self._on_changed)
        layout.addWidget(self._grid)

        # The known particle names, offered but never enforced. Absent on a
        # single-particle electrode, where the dict mode is still reachable
        # but has no names to suggest -- the plain "+" row is then the only
        # way to add one, which is exactly right.
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
            self._grid.add_toolbar_widget(button, align_right=False)

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
        return dict(self._rows())

    def commit_blocked_reason(self) -> str | None:
        seen: set[str] = set()
        for key, _ in self._rows():
            if key in seen:
                return f'Duplicate material "{key}" - each material may appear only once.'
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

    def pending_grid(self):
        return self._grid


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


def _domain_label(text: str) -> QLabel:
    """A quiet caption for the preview-domain row -- same treatment as the
    chart legend's own small labels (``table_preview._legend_label``)."""
    label = QLabel(text)
    label.setStyleSheet(f"color: {MUTED}; {typography.size_qss(typography.META)}")
    return label


def _format_domain_bound(value: float) -> str:
    """A compact preview-domain bound, trailing zeros trimmed -- the same
    ``%g`` convention chart axis ticks already use (``chart_axes.style_axis``)."""
    return f"{value:g}"


def _reference_series_id(pin) -> str:
    """The chart series id for a pinned reference's function overlay,
    stable for as long as the reference stays pinned at this position
    (``ReferencePin.index`` is unique within one pin list)."""
    return f"ref-{pin.index}"


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


def table_rows(value: object) -> list[list[object]]:
    """Zip a ``{"x": [...], "y": [...]}`` dict into grid rows.

    Only ever called with a value the registry judged representable, or with
    ``None``/anything else for an unseeded body, which yields an empty grid --
    the same fallback ``ParameterCard`` relies on to extract a reference's
    rows without hand-rolling a second table parser.
    """
    if not isinstance(value, dict):
        return []
    xs, ys = value.get("x"), value.get("y")
    if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != len(ys):
        return []
    return [[x, y] for x, y in zip(xs, ys, strict=False)]
