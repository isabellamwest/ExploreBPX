"""``DatabaseExamplesDialog``: compare a Validation run against bundled examples.

A read-only, disposable viewer -- it never mutates anything passed to it,
never commits, and holds no state that survives being closed (reopening
starts fresh: no persistence, no ``DocumentSession``, no new state-layer
object of any kind). That is an explicit architecture decision, not an
oversight: this dialog exists purely to let a modeller eyeball their own run
beside a handful of bundled reference runs from :mod:`core.example_library`,
nothing more.

**Layout.** A static picker on the left (today only four runs exist across
two documents, so there is nothing worth collapsing); a Chart/Table toggle
and a removable-chip legend on the right, over either three stacked
:class:`~.multi_series_chart.MultiSeriesChart` small multiples (Voltage,
Current, Temperature, all against Time) or a single read-only table of
whichever series is selected.

**Colour policy.** "You" (the card's own live draft, when given) always
renders in the app's own ``ACCENT`` and never competes for a slot in
``_REFERENCE_COLORS``; reference runs take the lowest free slot in that
fixed list, capped at :data:`MAX_REFERENCE_RUNS` concurrently-added runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.example_library import ExampleRun, list_example_runs, load_example_run

from ..style import ACCENT, BORDER, ERROR
from .modal import ModeStrip
from .multi_series_chart import MultiSeriesChart
from .values import format_value

_TIME = "Time [s]"
_TEMPERATURE = "Temperature [K]"
#: Table/chart column order. Deliberately a private copy of
#: ``experiment.KNOWN_ALIASES`` rather than an import of it: this dialog is
#: imported *by* ``experiment.py`` (it opens this dialog), so importing the
#: other way round would be a circular import -- and the two lists mean
#: different things anyway (one is bpx.schema field order, this one is
#: display order for a viewer with no schema of its own).
_KNOWN_ALIASES = (_TIME, "Current [A]", "Voltage [V]", _TEMPERATURE)

#: The sentinel id for "You" (the card's own live draft) in every dict here
#: keyed by series id -- distinct from any real ``ExampleRun.id``, which
#: always contains "::".
_YOU_ID = "__you__"

#: Categorical colours assigned to reference runs, in fixed *slot* order
#: (see ``DatabaseExamplesDialog._toggle_run``): the first run added takes
#: slot 0, and removing a run frees its slot for the next add rather than
#: shifting anyone else's colour. From the project's dataviz skill's
#: validated categorical palette (green / magenta / yellow / aqua) --
#: deliberately skipping the palette's blue slot, which ``ACCENT`` (the
#: colour "You" always renders in) already occupies, so a future reader must
#: not "restore" blue here.
_REFERENCE_COLORS = ("#008300", "#e87ba4", "#eda100", "#1baf7a")

#: How many reference runs (not counting "You", which never takes a slot)
#: can be compared at once -- one per ``_REFERENCE_COLORS`` entry.
MAX_REFERENCE_RUNS = len(_REFERENCE_COLORS)

_YOU_WIDTH = 3.0
_REFERENCE_WIDTH = 2.0


@dataclass(frozen=True)
class _AddedSeries:
    """One row currently in the comparison: its legend label, its raw array
    dict (same shape as ``core.example_library.load_example_run``'s return),
    and the colour it renders in."""

    label: str
    data: dict[str, list]
    color: str


def _is_plottable(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _points(data: dict[str, list], y_key: str) -> list[tuple[float, float]]:
    """Numeric ``(Time, y)`` pairs from *data*, x-sorted -- the exact
    contract ``MultiSeriesChart.set_series`` documents. A non-numeric or
    missing cell is dropped, never plotted as garbage or coerced: this is a
    read-only comparison viewer, not a validity judgement, so the grid and
    the validator remain the only places a bad cell is ever flagged."""
    time = data.get(_TIME) or []
    values = data.get(y_key) or []
    pairs = [
        (float(t), float(v))
        for t, v in zip(time, values)
        if _is_plottable(t) and _is_plottable(v)
    ]
    pairs.sort(key=lambda point: point[0])
    return pairs


class _AddToggle(QToolButton):
    """Round add/remove control on one picker row: "+" while the run is not
    in the comparison, a filled coloured check once it is."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setFixedSize(22, 22)
        self.set_removed()

    def set_removed(self) -> None:
        self.setText("+")
        self.setStyleSheet("")
        self.setToolTip("Add to the comparison")

    def set_added(self, color: str) -> None:
        self.setText("✓")
        self.setStyleSheet(
            f"QToolButton {{ background: {color}; color: #ffffff; "
            "border-radius: 11px; border: none; }"
        )
        self.setToolTip("Remove from the comparison")


class _LegendChip(QFrame):
    """One legend entry: colour swatch + label, over the added series'
    ``series_id``. Clicking the chip body selects it for Table mode; the
    trailing "x" removes it from the comparison -- two independent click
    targets on one small widget, so removing never gets mistaken for
    selecting."""

    clicked = Signal()
    remove_requested = Signal()

    def __init__(self, series_id: str, label: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.series_id = series_id
        self.color = color
        self.setObjectName("DatabaseExampleChip")
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(6)

        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background: {color}; border-radius: 5px;")
        layout.addWidget(swatch)

        layout.addWidget(QLabel(label))

        remove = QToolButton()
        remove.setText("×")
        remove.setAutoRaise(True)
        remove.setToolTip(f"Remove {label} from the comparison")
        remove.clicked.connect(lambda checked=False: self.remove_requested.emit())
        layout.addWidget(remove)

        self._selected = False
        self.set_selected(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        border = f"2px solid {ACCENT}" if selected else f"1px solid {BORDER}"
        self.setStyleSheet(
            f"QFrame#DatabaseExampleChip {{ border: {border}; border-radius: 8px; "
            "background: #ffffff; }"
        )

    @property
    def is_selected(self) -> bool:
        return self._selected


class _ChartPage(QWidget):
    """Three stacked small multiples, one per array, sharing Time [s] as
    their x-axis. The Temperature panel's own visibility is the caller's
    call (not every added series has one) -- this page just owns the three
    charts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.voltage = MultiSeriesChart(height=180)
        self.voltage.set_axis_titles(_TIME, "Voltage [V]")
        self.current = MultiSeriesChart(height=180)
        self.current.set_axis_titles(_TIME, "Current [A]")
        self.temperature = MultiSeriesChart(height=180)
        self.temperature.set_axis_titles(_TIME, _TEMPERATURE)

        layout.addWidget(self.voltage)
        layout.addWidget(self.current)
        layout.addWidget(self.temperature)
        layout.addStretch(1)


def _build_table() -> QTableWidget:
    table = QTableWidget(0, 0)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionMode(QTableWidget.NoSelection)
    return table


class DatabaseExamplesDialog(QDialog):
    """Overlay bundled reference runs against "You" (the card's own live
    draft), by chart or by table -- see the module docstring."""

    def __init__(
        self,
        own_run: dict[str, list] | None = None,
        own_label: str = "You",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add database examples")
        self.resize(1000, 760)

        #: ``series_id -> _AddedSeries`` for every run currently in the
        #: comparison, in the order it was added. "You" (when present) is
        #: always the first entry, added below before the first refresh.
        self._added: dict[str, _AddedSeries] = {}
        #: Fixed colour slots (see ``_REFERENCE_COLORS``): ``None`` when
        #: free, else the reference run id occupying it.
        self._reference_slots: list[str | None] = [None] * len(_REFERENCE_COLORS)
        self._selected_table_id: str | None = None
        self._view_mode = "chart"
        self._toggle_buttons: dict[str, _AddToggle] = {}
        self._chips: dict[str, _LegendChip] = {}

        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        body.addWidget(self._build_picker())
        body.addLayout(self._build_viewer(), 1)
        layout.addLayout(body, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

        if own_run is not None:
            self._added[_YOU_ID] = _AddedSeries(own_label, dict(own_run), ACCENT)
        self._after_change()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_picker(self) -> QWidget:
        container = QWidget()
        container.setFixedWidth(230)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)

        heading = QLabel("Bundled examples")
        heading.setObjectName("Heading")
        layout.addWidget(heading)

        runs_by_document: dict[str, list[ExampleRun]] = {}
        document_order: list[str] = []
        for run in list_example_runs():
            if run.document_id not in runs_by_document:
                runs_by_document[run.document_id] = []
                document_order.append(run.document_id)
            runs_by_document[run.document_id].append(run)

        for document_id in document_order:
            runs = runs_by_document[document_id]
            group_header = QLabel(f"{runs[0].short_title} · {runs[0].model}")
            group_header.setObjectName("Heading")
            group_header.setWordWrap(True)
            layout.addWidget(group_header)
            for run in runs:
                layout.addLayout(self._picker_row(run))

        self._cap_message = QLabel("")
        self._cap_message.setStyleSheet(f"color: {ERROR}; font-size: 11px;")
        self._cap_message.setWordWrap(True)
        self._cap_message.hide()
        layout.addWidget(self._cap_message)
        layout.addStretch(1)
        return container

    def _picker_row(self, run: ExampleRun) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel(f"{run.run_name} · {run.point_count} pts")
        label.setWordWrap(True)
        row.addWidget(label, 1)
        toggle = _AddToggle()
        toggle.clicked.connect(lambda checked=False, r=run: self._toggle_run(r))
        self._toggle_buttons[run.id] = toggle
        row.addWidget(toggle)
        return row

    def _build_viewer(self) -> QVBoxLayout:
        layout = QVBoxLayout()

        toolbar = QHBoxLayout()
        self._mode_strip = ModeStrip(("Chart", "Table"), self._on_mode_clicked)
        toolbar.addWidget(self._mode_strip)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self._mode_strip.select(0)

        legend_container = QWidget()
        self._legend_layout = QHBoxLayout(legend_container)
        self._legend_layout.setContentsMargins(0, 4, 0, 4)
        self._legend_layout.setSpacing(6)
        layout.addWidget(legend_container)

        self._hint_label = QLabel("Pick a run on the left to compare it here.")
        self._hint_label.setObjectName("Hint")
        self._hint_label.setAlignment(Qt.AlignCenter)

        self._chart_page = _ChartPage()
        self._table = _build_table()

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._hint_label)
        self._view_stack.addWidget(self._chart_page)
        self._view_stack.addWidget(self._table)
        layout.addWidget(self._view_stack, 1)

        return layout

    # ------------------------------------------------------------------
    # Add / remove
    # ------------------------------------------------------------------

    def _toggle_run(self, run: ExampleRun) -> None:
        if run.id in self._added:
            self._remove_series(run.id)
            return
        slot = next((i for i, occupant in enumerate(self._reference_slots) if occupant is None), None)
        if slot is None:
            self._cap_message.setText(
                f"Up to {MAX_REFERENCE_RUNS} reference runs at a time -- remove one to add another."
            )
            self._cap_message.show()
            return
        self._cap_message.hide()
        self._reference_slots[slot] = run.id
        color = _REFERENCE_COLORS[slot]
        self._added[run.id] = _AddedSeries(
            f"{run.model} · {run.run_name}", load_example_run(run.id), color
        )
        self._toggle_buttons[run.id].set_added(color)
        self._after_change()

    def _remove_series(self, series_id: str) -> None:
        if series_id not in self._added:
            return
        del self._added[series_id]
        if series_id in self._reference_slots:
            self._reference_slots[self._reference_slots.index(series_id)] = None
        toggle = self._toggle_buttons.get(series_id)
        if toggle is not None:
            toggle.set_removed()
        self._cap_message.hide()
        self._after_change()

    def _after_change(self) -> None:
        if self._selected_table_id not in self._added:
            self._selected_table_id = self._default_table_selection()
        self._refresh_all()

    def _default_table_selection(self) -> str | None:
        if _YOU_ID in self._added:
            return _YOU_ID
        others = [series_id for series_id in self._added if series_id != _YOU_ID]
        return others[0] if others else None

    def _select_table_series(self, series_id: str) -> None:
        if series_id not in self._added or series_id == self._selected_table_id:
            return
        self._selected_table_id = series_id
        self._refresh_legend()
        self._refresh_table()

    # ------------------------------------------------------------------
    # Chart/Table toggle
    # ------------------------------------------------------------------

    def _on_mode_clicked(self, index: int) -> None:
        self._view_mode = "table" if index == 1 else "chart"
        self._refresh_view()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        self._refresh_legend()
        self._refresh_charts()
        self._refresh_table()
        self._refresh_view()

    def _refresh_legend(self) -> None:
        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._chips = {}
        for series_id, added in self._added.items():
            chip = _LegendChip(series_id, added.label, added.color)
            chip.set_selected(series_id == self._selected_table_id)
            chip.clicked.connect(lambda sid=series_id: self._select_table_series(sid))
            chip.remove_requested.connect(lambda sid=series_id: self._remove_series(sid))
            self._legend_layout.addWidget(chip)
            self._chips[series_id] = chip
        self._legend_layout.addStretch(1)

    def _refresh_charts(self) -> None:
        page = self._chart_page
        page.voltage.clear()
        page.current.clear()
        page.temperature.clear()
        has_temperature = any(_TEMPERATURE in added.data for added in self._added.values())
        page.temperature.setVisible(has_temperature and page.temperature.available)
        for series_id, added in self._added.items():
            width = _YOU_WIDTH if series_id == _YOU_ID else _REFERENCE_WIDTH
            page.voltage.set_series(series_id, _points(added.data, "Voltage [V]"), added.color, width)
            page.current.set_series(series_id, _points(added.data, "Current [A]"), added.color, width)
            if _TEMPERATURE in added.data:
                page.temperature.set_series(
                    series_id, _points(added.data, _TEMPERATURE), added.color, width
                )

    def _refresh_table(self) -> None:
        table = self._table
        table.clear()
        if self._selected_table_id is None:
            table.setRowCount(0)
            table.setColumnCount(0)
            return
        data = self._added[self._selected_table_id].data
        columns = [key for key in _KNOWN_ALIASES if key in data]
        row_count = max((len(data.get(key) or []) for key in columns), default=0)
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(row_count)
        for c, key in enumerate(columns):
            values = data.get(key) or []
            for r in range(row_count):
                value = values[r] if r < len(values) else None
                item = QTableWidgetItem(format_value(value))
                item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if value is not None and not isinstance(value, (int, float)):
                    item.setForeground(Qt.red)
                table.setItem(r, c, item)

    def _refresh_view(self) -> None:
        if not self._added:
            self._view_stack.setCurrentWidget(self._hint_label)
        elif self._view_mode == "table":
            self._view_stack.setCurrentWidget(self._table)
        else:
            self._view_stack.setCurrentWidget(self._chart_page)
