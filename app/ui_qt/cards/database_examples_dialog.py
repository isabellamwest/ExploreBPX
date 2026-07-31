"""``DatabaseExamplesDialog``: compare a Validation run against reference data.

A read-only, disposable viewer -- it never mutates anything passed to it,
never commits, and holds no state that survives being closed (reopening
starts fresh: no persistence, no ``DocumentSession``, no new state-layer
object of any kind). That is an explicit architecture decision, not an
oversight: this dialog exists purely to let a modeller eyeball their own run
beside reference runs -- the bundled sample cells from
:mod:`core.example_library`, or any BPX file they open -- nothing more.

**Layout** (Concept A, approved 2026-07-20). A picker on the left: the
bundled sample runs grouped by cell, then any user-opened files, then an
"Open BPX file…" button. A run is added/removed by clicking its row -- the
row is a plain box that gains a border in its series colour and a small
tick while added (standing rule: never circled tick/cross badges anywhere
in the app). On the right: a Chart/Table toggle and a removable-chip
legend, over either three stacked
:class:`~.multi_series_chart.MultiSeriesChart` small multiples (Voltage,
Current, Temperature, all against Time) with a key-numbers table beneath
(points, duration, current/voltage range -- stated facts only, no computed
diffs), or a single read-only table of whichever series is selected.

**Colour policy.** "You" (the card's own live draft, when it has any data)
always renders in the app's own ``ACCENT`` and never competes for a slot in
``_REFERENCE_COLORS``; reference runs take the lowest free slot in that
fixed list, capped at :data:`MAX_REFERENCE_RUNS` concurrently-added runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.bpx_gateway import LoadError, expected_fields
from core.example_library import (
    ExampleRun,
    list_example_runs,
    load_example_run,
    load_reference_document,
)
from core.values import format_value

from ..style import ACCENT, BORDER, ERROR, MUTED
from ..titles import panel_title
from .modal import ModeStrip
from .multi_series_chart import MultiSeriesChart

_TIME = "Time [s]"
_TEMPERATURE = "Temperature [K]"
#: Table/chart column order: the Experiment schema's own field order, derived
#: through the gateway -- the same derivation as ``experiment.KNOWN_ALIASES``,
#: repeated here rather than imported because this dialog is imported *by*
#: ``experiment.py`` (it opens this dialog), so importing the other way round
#: would be a circular import. ``_TIME``/``_TEMPERATURE`` stay literal: they
#: are this viewer's display choices (x-axis, optional column), not a schema
#: restatement.
_KNOWN_ALIASES = tuple(
    f.alias for f in expected_fields(("Validation", "<run>"))
)

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

_NO_OWN_DATA_NOTICE = "No data in this experiment yet - showing reference data only."


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


def _numeric(values: object) -> list[float]:
    """The plottable numbers in one raw column, order preserved."""
    if not isinstance(values, list):
        return []
    return [float(v) for v in values if _is_plottable(v)]


def _format_duration(seconds: float) -> str:
    """A duration stated at reading precision: hours above an hour, minutes
    above a minute, else seconds -- presentation formatting of a plain fact,
    not a spec quantity."""
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} h"
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.0f} s"


def _format_range(values: list[float], unit: str) -> str:
    """"2.9 to 4.19 V", collapsing to one value when the column never
    varies. " to " rather than an en dash: current ranges are routinely
    negative-to-negative ("-12.5–-0.0058 A" is unreadable, seen in the
    real-app proof). "-" for a column with no numeric values (never a
    judgement -- the grid and validator flag bad cells; this table only
    states what is there)."""
    if not values:
        return "-"
    lo, hi = min(values), max(values)
    low, high = f"{lo:.4g}", f"{hi:.4g}"
    if low == high:
        return f"{low} {unit}"
    return f"{low} to {high} {unit}"


class _PickerRow(QFrame):
    """One selectable reference run: a plain box row that gains a border in
    its series colour plus a small tick while the run is in the comparison.

    Standing rule (Bella, 2026-07-20): selection is a highlighted box with
    at most a small plain tick -- never a circled +/tick/cross badge."""

    clicked = Signal()

    def __init__(self, run: ExampleRun, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ReferencePickerRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        name = QLabel(run.run_name)
        name.setWordWrap(True)
        layout.addWidget(name, 1)

        points = QLabel(f"{run.point_count} pts")
        points.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        layout.addWidget(points)

        self._tick = QLabel("✓")
        self._tick.hide()
        layout.addWidget(self._tick)

        self.set_removed()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def set_removed(self) -> None:
        self._tick.hide()
        self.setStyleSheet(
            f"QFrame#ReferencePickerRow {{ border: 1px solid {BORDER}; "
            "border-radius: 4px; }"
        )
        self.setToolTip("Add to the comparison")

    def set_added(self, color: str) -> None:
        self._tick.setStyleSheet(f"color: {color}; font-weight: 600;")
        self._tick.show()
        self.setStyleSheet(
            f"QFrame#ReferencePickerRow {{ border: 2px solid {color}; "
            "border-radius: 4px; }"
        )
        self.setToolTip("Remove from the comparison")


class _LegendChip(QFrame):
    """One legend entry: colour swatch + label, over the added series'
    ``series_id``. Clicking the chip body selects it for Table mode; a
    *removable* chip also carries a trailing "x" that drops it from the
    comparison -- two independent click targets on one small widget, so
    removing never gets mistaken for selecting.

    The active document's own run is **not** removable: it is the anchor the
    whole dialog compares against, and -- unlike a reference run -- it has no
    picker row to add it back from, so a removed one would be gone for good
    (the bug Bella hit 2026-07-20). Its chip therefore has no "x"."""

    clicked = Signal()
    remove_requested = Signal()

    def __init__(
        self,
        series_id: str,
        label: str,
        color: str,
        removable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.series_id = series_id
        self.color = color
        self.removable = removable
        self.setObjectName("DatabaseExampleChip")
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4 if removable else 8, 2)
        layout.setSpacing(6)

        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background: {color}; border-radius: 5px;")
        layout.addWidget(swatch)

        layout.addWidget(QLabel(label))

        if removable:
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
            f"QFrame#DatabaseExampleChip {{ border: {border}; border-radius: 6px; "
            "background: #ffffff; }"
        )

    @property
    def is_selected(self) -> bool:
        return self._selected


class _ChartPage(QWidget):
    """Three stacked small multiples, one per array, sharing Time [s] as
    their x-axis, with the key-numbers table beneath. The Temperature
    panel's own visibility is the caller's call (not every added series has
    one) -- this page just owns the widgets."""

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

        self.numbers = _build_table()
        self.numbers.setObjectName("CompareNumbersTable")
        layout.addWidget(self.numbers)
        layout.addStretch(1)


def _build_table() -> QTableWidget:
    table = QTableWidget(0, 0)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionMode(QTableWidget.NoSelection)
    return table


class DatabaseExamplesDialog(QDialog):
    """Overlay reference runs against the active document's own run (the
    card's live draft, labelled by file name -- never "You", Bella's call
    2026-07-20), by chart or by table -- see the module docstring."""

    def __init__(
        self,
        own_run: dict[str, list] | None = None,
        own_label: str = "Active file",
        run_label: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            f"Compare - Experiment · {run_label}" if run_label else "Compare experiment data"
        )
        self.resize(1000, 760)

        #: ``series_id -> _AddedSeries`` for every run currently in the
        #: comparison, in the order it was added. "You" (when it has data)
        #: is always the first entry, added below before the first refresh.
        self._added: dict[str, _AddedSeries] = {}
        #: Fixed colour slots (see ``_REFERENCE_COLORS``): ``None`` when
        #: free, else the reference run id occupying it.
        self._reference_slots: list[str | None] = [None] * len(_REFERENCE_COLORS)
        self._selected_table_id: str | None = None
        self._view_mode = "chart"
        self._picker_rows: dict[str, _PickerRow] = {}
        self._chips: dict[str, _LegendChip] = {}
        #: ``ExampleRun.id -> raw array dict`` for runs from user-opened
        #: files (bundled runs re-read from disk via ``load_example_run``
        #: instead -- see ``_run_data``), plus a counter making each open's
        #: ``document_id`` unique even for the same file twice.
        self._file_data: dict[str, dict] = {}
        self._file_count = 0

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

        has_own_data = own_run is not None and any(
            isinstance(values, list) and len(values) > 0 for values in own_run.values()
        )
        if has_own_data:
            self._added[_YOU_ID] = _AddedSeries(own_label, dict(own_run), ACCENT)
        # An empty run is stated plainly rather than silently lacking a
        # "You" curve -- the exact confusion the pre-redesign dialog caused.
        self._own_notice.setVisible(not has_own_data)
        self._after_change()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_picker(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(5)

        heading = panel_title("Sample data")
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
            self._add_picker_group(layout, runs[0].short_title, runs)

        #: User-opened files append their groups here, between the bundled
        #: samples and the "Open BPX file…" button.
        self._file_groups = QVBoxLayout()
        self._file_groups.setSpacing(5)
        layout.addLayout(self._file_groups)

        open_button = QPushButton("Open BPX file…")
        open_button.setObjectName("CompareOpenFileButton")
        open_button.setToolTip(
            "Add the validation runs of another BPX file to this comparison"
        )
        open_button.clicked.connect(self._open_reference_file)
        layout.addWidget(open_button)

        self._file_message = QLabel("")
        self._file_message.setStyleSheet(f"color: {ERROR}; font-size: 11px;")
        self._file_message.setWordWrap(True)
        self._file_message.hide()
        layout.addWidget(self._file_message)

        self._cap_message = QLabel("")
        self._cap_message.setStyleSheet(f"color: {ERROR}; font-size: 11px;")
        self._cap_message.setWordWrap(True)
        self._cap_message.hide()
        layout.addWidget(self._cap_message)
        layout.addStretch(1)

        # Scrollable so opened files can never push rows out of reach; the
        # picker itself stays a fixed-width rail.
        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setFixedWidth(250)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll

    def _add_picker_group(
        self, layout: QVBoxLayout, heading: str, runs: list[ExampleRun]
    ) -> None:
        group_header = QLabel(heading)
        group_header.setObjectName("Heading")
        group_header.setWordWrap(True)
        layout.addWidget(group_header)
        for run in runs:
            row = _PickerRow(run)
            row.clicked.connect(lambda r=run: self._toggle_run(r))
            self._picker_rows[run.id] = row
            layout.addWidget(row)

    def _build_viewer(self) -> QVBoxLayout:
        layout = QVBoxLayout()

        toolbar = QHBoxLayout()
        self._own_notice = QLabel(_NO_OWN_DATA_NOTICE)
        self._own_notice.setObjectName("CompareOwnDataNotice")
        self._own_notice.setStyleSheet(f"color: {MUTED};")
        toolbar.addWidget(self._own_notice)
        toolbar.addStretch(1)
        self._mode_strip = ModeStrip(("Chart", "Table"), self._on_mode_clicked)
        toolbar.addWidget(self._mode_strip)
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
        # Raw-data view: columns stretch to fill the width, matching the
        # NumericGrid look (the numbers table instead fits to its contents).
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._hint_label)
        self._view_stack.addWidget(self._chart_page)
        self._view_stack.addWidget(self._table)
        layout.addWidget(self._view_stack, 1)

        return layout

    # ------------------------------------------------------------------
    # Add / remove
    # ------------------------------------------------------------------

    def _run_data(self, run: ExampleRun) -> dict[str, list]:
        if run.id in self._file_data:
            return self._file_data[run.id]
        return load_example_run(run.id)

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
            f"{run.short_title} · {run.run_name}", self._run_data(run), color
        )
        self._picker_rows[run.id].set_added(color)
        self._after_change()

    def _remove_series(self, series_id: str) -> None:
        # The active document's own run is the non-removable anchor (see
        # ``_LegendChip``): it has no picker row to re-add it from, so it must
        # never leave ``_added``. Its chip carries no "x", but guard here too.
        if series_id == _YOU_ID or series_id not in self._added:
            return
        del self._added[series_id]
        if series_id in self._reference_slots:
            self._reference_slots[self._reference_slots.index(series_id)] = None
        row = self._picker_rows.get(series_id)
        if row is not None:
            row.set_removed()
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
    # "Open BPX file…"
    # ------------------------------------------------------------------

    def _open_reference_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open BPX file",
            "",
            "BPX files (*.json *.yaml *.yml);;All files (*)",
        )
        if path:
            self._add_reference_file(path)

    def _add_reference_file(self, path: str) -> None:
        """Append *path*'s validation runs to the picker, or say plainly why
        not -- decode failures surface the gateway's own message verbatim
        (validator fidelity: this dialog never rewords what ``bpx_gateway``
        reports)."""
        file_path = Path(path)
        self._file_count += 1
        try:
            document = load_reference_document(
                file_path.read_bytes(), file_path.name, f"file:{self._file_count}"
            )
        except OSError as exc:
            self._show_file_message(f"Could not read {file_path.name}: {exc}")
            return
        except LoadError as exc:
            self._show_file_message(f"{file_path.name}: {exc}")
            return
        if not document.runs:
            self._show_file_message(
                f"{file_path.name} has no validation runs to compare."
            )
            return
        self._file_message.hide()
        for run in document.runs:
            self._file_data[run.id] = document.data[run.run_name]
        self._add_picker_group(self._file_groups, document.label, list(document.runs))

    def _show_file_message(self, message: str) -> None:
        self._file_message.setText(message)
        self._file_message.show()

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
        self._refresh_numbers()
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
            chip = _LegendChip(
                series_id, added.label, added.color, removable=series_id != _YOU_ID
            )
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

    def _refresh_numbers(self) -> None:
        """The key-numbers table under the charts: one row per added series,
        stating points, duration and current/voltage range. Plain min/max/
        count arithmetic on what is plotted -- factual summaries, never a
        computed diff or a validity judgement."""
        table = self._chart_page.numbers
        table.clear()
        headers = ("Run", "Points", "Duration", "Current", "Voltage")
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(self._added))
        table.verticalHeader().hide()
        for r, (series_id, added) in enumerate(self._added.items()):
            time = _numeric(added.data.get(_TIME))
            duration = _format_duration(max(time) - min(time)) if time else "-"
            name = QTableWidgetItem(added.label)
            name.setData(Qt.DecorationRole, QColor(added.color))
            cells = (
                name,
                QTableWidgetItem(str(len(added.data.get(_TIME) or []))),
                QTableWidgetItem(duration),
                QTableWidgetItem(_format_range(_numeric(added.data.get("Current [A]")), "A")),
                QTableWidgetItem(_format_range(_numeric(added.data.get("Voltage [V]")), "V")),
            )
            for c, item in enumerate(cells):
                if c > 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        header_height = table.horizontalHeader().height()
        rows_height = sum(table.rowHeight(r) for r in range(table.rowCount()))
        table.setFixedHeight(header_height + rows_height + 2 * table.frameWidth())
        table.setVisible(bool(self._added))

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
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if value is not None and not isinstance(value, (int, float)):
                    item.setForeground(QColor(ERROR))
                table.setItem(r, c, item)

    def _refresh_view(self) -> None:
        if not self._added:
            self._view_stack.setCurrentWidget(self._hint_label)
        elif self._view_mode == "table":
            self._view_stack.setCurrentWidget(self._table)
        else:
            self._view_stack.setCurrentWidget(self._chart_page)
