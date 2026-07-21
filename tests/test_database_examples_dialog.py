"""DatabaseExamplesDialog: read-only comparison viewer over bundled examples
plus any user-opened BPX file.

Constructed directly and inspected, never through ``.exec()`` -- this is a
disposable viewer with nothing to confirm back to a caller, so there is
nothing gained by opening a real blocking modal loop just to test it (the
non-blocking idiom the feature's own spec calls for).
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton

from core.example_library import ExampleRun, list_example_runs, load_reference_document
from ui_qt.cards import database_examples_dialog as dialog_module
from ui_qt.cards.database_examples_dialog import (
    MAX_REFERENCE_RUNS,
    DatabaseExamplesDialog,
)
from ui_qt.style import ACCENT

_OWN_RUN = {
    "Time [s]": [0, 1, 2],
    "Current [A]": [-1.0, -1.0, -1.0],
    "Voltage [V]": [4.0, 3.9, 3.8],
}

#: The full bundled catalog, two documents (NMC pouch cell, LFP 18650 cell)
#: x five runs each -- see ``test_example_library.py``. None of them carry
#: Temperature (the About:Energy source data doesn't), so temperature-panel
#: coverage below fabricates one run instead (see ``_with_temperature_run``).
_BUNDLED_RUN_COUNT = 10


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


def _first_run() -> ExampleRun:
    return list_example_runs()[0]


def _synthetic_run_with_temperature() -> ExampleRun:
    """A fabricated run carrying Temperature -- the real bundled About:Energy
    runs never have one (see the module docstring's ``_BUNDLED_RUN_COUNT``
    note), so temperature-panel coverage needs one synthesised the same way
    the cap-refusal test synthesises an extra run."""
    real = list_example_runs()[0]
    return ExampleRun(
        id="about_energy/nmc_pouch_cell::Synthetic run",
        document_id=real.document_id,
        document_title=real.document_title,
        short_title=real.short_title,
        model=real.model,
        run_name="Synthetic run",
        point_count=3,
        has_temperature=True,
    )


_SYNTHETIC_TEMPERATURE_DATA = {
    "Time [s]": [0, 1, 2],
    "Current [A]": [-1.0, -1.0, -1.0],
    "Voltage [V]": [4.0, 3.9, 3.8],
    "Temperature [K]": [298.0, 298.5, 299.0],
}


@pytest.fixture
def _with_temperature_run(monkeypatch) -> ExampleRun:
    """Adds :func:`_synthetic_run_with_temperature` to the catalog the dialog
    sees, alongside the real bundled runs, and serves its fabricated data
    when the dialog asks to load it."""
    run = _synthetic_run_with_temperature()
    real_runs = list_example_runs()
    real_load = dialog_module.load_example_run
    monkeypatch.setattr(dialog_module, "list_example_runs", lambda: (*real_runs, run))
    monkeypatch.setattr(
        dialog_module,
        "load_example_run",
        lambda run_id: dict(_SYNTHETIC_TEMPERATURE_DATA) if run_id == run.id else real_load(run_id),
    )
    return run


def test_with_no_own_run_nothing_is_added_and_the_hint_shows():
    dialog = DatabaseExamplesDialog()

    assert dialog._added == {}
    assert dialog._view_stack.currentWidget() is dialog._hint_label


def test_own_run_is_added_first_in_accent_and_never_takes_a_reference_slot():
    dialog = DatabaseExamplesDialog(_OWN_RUN, "my_cell · test run")

    assert list(dialog._added) == ["__you__"]
    added = dialog._added["__you__"]
    assert added.color == ACCENT
    assert added.label == "my_cell · test run"
    assert dialog._reference_slots == [None] * MAX_REFERENCE_RUNS


def test_adding_a_reference_run_gets_the_first_palette_colour_and_a_chip():
    dialog = DatabaseExamplesDialog()
    run = _first_run()

    dialog._toggle_run(run)

    assert dialog._added[run.id].color == "#008300"
    assert run.id in dialog._chips
    assert dialog._chips[run.id].color == "#008300"
    # The picker row reflects "added" too: a coloured border plus a tick,
    # never a circled +/tick badge (standing rule -- see _PickerRow).
    assert not dialog._picker_rows[run.id]._tick.isHidden()


def test_adding_a_reference_run_adds_its_curve_to_voltage_and_current_charts():
    dialog = DatabaseExamplesDialog()
    run = _first_run()

    dialog._toggle_run(run)

    page = dialog._chart_page
    assert run.id in page.voltage._series
    assert run.id in page.current._series


def test_removing_a_run_removes_its_chip_and_its_curves():
    dialog = DatabaseExamplesDialog()
    run = _first_run()
    dialog._toggle_run(run)

    dialog._remove_series(run.id)

    assert run.id not in dialog._added
    assert run.id not in dialog._chips
    page = dialog._chart_page
    assert run.id not in page.voltage._series
    assert run.id not in page.current._series
    assert dialog._picker_rows[run.id]._tick.isHidden()


def test_removing_a_run_frees_its_colour_slot_for_the_next_add():
    dialog = DatabaseExamplesDialog()
    runs = list_example_runs()

    dialog._toggle_run(runs[0])
    assert dialog._added[runs[0].id].color == "#008300"

    dialog._remove_series(runs[0].id)
    dialog._toggle_run(runs[1])

    assert dialog._added[runs[1].id].color == "#008300"


def test_picker_row_tick_shows_while_added_and_hides_when_removed():
    dialog = DatabaseExamplesDialog()
    run = _first_run()
    row = dialog._picker_rows[run.id]
    assert row._tick.isHidden()

    dialog._toggle_run(run)
    assert not row._tick.isHidden()

    dialog._remove_series(run.id)
    assert row._tick.isHidden()


def test_a_fifth_reference_run_is_refused():
    """The bundled catalog now has ten real runs, so the cap (four) is
    exercised with real runs -- no fabrication needed."""
    dialog = DatabaseExamplesDialog()
    runs = list_example_runs()
    assert len(runs) == _BUNDLED_RUN_COUNT

    for run in runs[:MAX_REFERENCE_RUNS]:
        dialog._toggle_run(run)
    assert dialog._cap_message.isHidden()

    fifth = runs[MAX_REFERENCE_RUNS]
    dialog._toggle_run(fifth)

    assert fifth.id not in dialog._added
    assert not dialog._cap_message.isHidden()
    assert str(MAX_REFERENCE_RUNS) in dialog._cap_message.text()


def test_chart_table_toggle_switches_the_visible_view():
    dialog = DatabaseExamplesDialog(_OWN_RUN)

    assert dialog._view_stack.currentWidget() is dialog._chart_page

    dialog._on_mode_clicked(1)
    assert dialog._view_stack.currentWidget() is dialog._table

    dialog._on_mode_clicked(0)
    assert dialog._view_stack.currentWidget() is dialog._chart_page


def test_default_table_selection_is_you_when_present():
    dialog = DatabaseExamplesDialog(_OWN_RUN)
    dialog._toggle_run(_first_run())

    assert dialog._selected_table_id == "__you__"


def test_default_table_selection_is_the_first_added_run_without_you():
    dialog = DatabaseExamplesDialog()
    run = _first_run()

    dialog._toggle_run(run)

    assert dialog._selected_table_id == run.id


def test_clicking_a_chip_selects_it_for_the_table():
    dialog = DatabaseExamplesDialog(_OWN_RUN)
    run = _first_run()
    dialog._toggle_run(run)
    assert dialog._selected_table_id == "__you__"

    dialog._select_table_series(run.id)

    assert dialog._selected_table_id == run.id
    assert dialog._chips[run.id].is_selected is True
    assert dialog._chips["__you__"].is_selected is False


def test_removing_the_selected_series_falls_back_to_the_default():
    dialog = DatabaseExamplesDialog(_OWN_RUN)
    run = _first_run()
    dialog._toggle_run(run)
    dialog._select_table_series(run.id)

    dialog._remove_series(run.id)

    assert dialog._selected_table_id == "__you__"


def test_table_omits_temperature_for_a_series_that_lacks_it():
    dialog = DatabaseExamplesDialog(_OWN_RUN)  # no Temperature key

    headers = [
        dialog._table.horizontalHeaderItem(c).text() for c in range(dialog._table.columnCount())
    ]

    assert headers == ["Time [s]", "Current [A]", "Voltage [V]"]
    assert dialog._table.rowCount() == 3


def test_table_shows_the_selected_series_full_data_including_temperature(
    _with_temperature_run,
):
    dialog = DatabaseExamplesDialog()
    run = _with_temperature_run
    dialog._toggle_run(run)
    dialog._on_mode_clicked(1)

    headers = [
        dialog._table.horizontalHeaderItem(c).text() for c in range(dialog._table.columnCount())
    ]
    assert headers == ["Time [s]", "Current [A]", "Voltage [V]", "Temperature [K]"]

    data = _SYNTHETIC_TEMPERATURE_DATA
    assert dialog._table.rowCount() == len(data["Time [s]"])
    assert dialog._table.item(0, 0).text() == str(data["Time [s]"][0])
    assert dialog._table.item(0, 3).text() == str(data["Temperature [K]"][0])


def test_adding_a_run_with_temperature_adds_its_curve_to_the_temperature_chart(
    _with_temperature_run,
):
    dialog = DatabaseExamplesDialog()
    run = _with_temperature_run

    dialog._toggle_run(run)

    assert run.id in dialog._chart_page.temperature._series


def test_temperature_panel_hidden_until_a_series_with_temperature_is_added(
    _with_temperature_run,
):
    dialog = DatabaseExamplesDialog(_OWN_RUN)  # the own run has no Temperature
    run = _with_temperature_run

    assert dialog._chart_page.temperature.isHidden()

    dialog._toggle_run(run)

    assert not dialog._chart_page.temperature.isHidden()

    dialog._remove_series(run.id)

    assert dialog._chart_page.temperature.isHidden()


def test_own_run_is_the_anchor_and_cannot_be_removed():
    """The active document's own run has no picker row to add it back from,
    so it is the non-removable anchor: its legend chip carries no "x", and
    ``_remove_series`` refuses it even if called directly (the dead-end Bella
    hit 2026-07-20)."""
    dialog = DatabaseExamplesDialog(_OWN_RUN, "my_cell · test run")

    assert dialog._chips["__you__"].removable is False

    dialog._remove_series("__you__")

    assert "__you__" in dialog._added
    assert dialog._selected_table_id == "__you__"


def test_a_reference_chip_stays_removable():
    """A reference run keeps its "x" -- it can be toggled back on from its
    picker row, so removing it is never a dead-end."""
    dialog = DatabaseExamplesDialog(_OWN_RUN, "my_cell · test run")
    dialog._toggle_run(_first_run())

    reference_id = next(sid for sid in dialog._chips if sid != "__you__")
    assert dialog._chips[reference_id].removable is True

    dialog._remove_series(reference_id)

    assert reference_id not in dialog._added


def test_own_run_carries_line_width_three_and_reference_runs_carry_two():
    dialog = DatabaseExamplesDialog(_OWN_RUN)
    run = _first_run()
    dialog._toggle_run(run)

    you_line = dialog._chart_page.voltage._series["__you__"]
    run_line = dialog._chart_page.voltage._series[run.id]
    assert you_line.pen().widthF() == 3.0
    assert run_line.pen().widthF() == 2.0


# ---------------------------------------------------------------------------
# Window title
# ---------------------------------------------------------------------------


def test_window_title_names_the_run_when_a_run_label_is_given():
    dialog = DatabaseExamplesDialog(run_label="C/20 discharge")

    assert dialog.windowTitle() == "Compare - Experiment · C/20 discharge"


def test_window_title_is_generic_without_a_run_label():
    dialog = DatabaseExamplesDialog()

    assert dialog.windowTitle() == "Compare experiment data"


# ---------------------------------------------------------------------------
# CompareOwnDataNotice: stated plainly whenever the own run has nothing to show
# ---------------------------------------------------------------------------


def test_own_notice_visible_with_no_own_run_at_all():
    dialog = DatabaseExamplesDialog()

    assert not dialog._own_notice.isHidden()


def test_own_notice_visible_when_the_own_run_has_every_column_but_no_values():
    empty_run = {"Time [s]": [], "Current [A]": [], "Voltage [V]": []}

    dialog = DatabaseExamplesDialog(empty_run)

    assert not dialog._own_notice.isHidden()


def test_own_notice_hidden_once_the_own_run_has_data():
    dialog = DatabaseExamplesDialog(_OWN_RUN)

    assert dialog._own_notice.isHidden()


# ---------------------------------------------------------------------------
# CompareNumbersTable: the key-numbers table beneath the charts
# ---------------------------------------------------------------------------


def test_numbers_table_hidden_until_something_is_added():
    dialog = DatabaseExamplesDialog()

    assert dialog._chart_page.numbers.isHidden()
    assert dialog._chart_page.numbers.rowCount() == 0


def test_numbers_table_reports_points_duration_and_ranges_for_own_run_and_a_reference():
    """Expected strings are hand-computed from the actual bundled data (see
    ``test_example_library.py``'s equivalent scrape) and from ``_OWN_RUN``
    above, not re-derived through the formatting helpers under test."""
    dialog = DatabaseExamplesDialog(_OWN_RUN, "my_cell · test run")
    # Pinned by id, not picker position -- the picker's curated order (NMC
    # first) is presentation, and these hand-computed values are the LFP
    # C/20 run's (1000 pts).
    run = next(
        r for r in list_example_runs()
        if r.id == "about_energy/lfp_18650_cell::C/20 discharge"
    )

    dialog._toggle_run(run)

    table = dialog._chart_page.numbers
    headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
    assert headers == ["Run", "Points", "Duration", "Current", "Voltage"]
    assert table.rowCount() == 2
    assert not table.isHidden()

    # Row 0: the own run -- 3 points spanning 2 s, constant current, 3.8-4 V.
    assert table.item(0, 0).text() == "my_cell · test run"
    assert table.item(0, 1).text() == "3"
    assert table.item(0, 2).text() == "2 s"
    assert table.item(0, 3).text() == "-1 A"
    assert table.item(0, 4).text() == "3.8 to 4 V"

    # Row 1: the added reference run -- 1000 points spanning ~20.7 h.
    assert table.item(1, 0).text() == "LFP 18650 cell · C/20 discharge"
    assert table.item(1, 1).text() == "1000"
    assert table.item(1, 2).text() == "20.7 h"
    assert table.item(1, 3).text() == "-0.1004 to -0.002607 A"
    assert table.item(1, 4).text() == "2 to 3.477 V"


# ---------------------------------------------------------------------------
# "Open BPX file…" / _add_reference_file
# ---------------------------------------------------------------------------


def test_open_bpx_file_button_is_present_and_named_for_the_driver():
    dialog = DatabaseExamplesDialog()

    button = dialog.findChild(QPushButton, "CompareOpenFileButton")

    assert button is not None


def test_add_reference_file_appends_a_picker_group_and_its_run_is_addable(tmp_path):
    payload = {
        "Header": {"BPX": "0.1.0", "Title": "My Test Cell", "Model": "DFN"},
        "Validation": {
            "My run": {
                "Time [s]": [0, 1, 2],
                "Current [A]": [-2.0, -2.0, -2.0],
                "Voltage [V]": [4.2, 4.1, 4.0],
            },
        },
    }
    path = tmp_path / "my_cell.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    dialog = DatabaseExamplesDialog()
    dialog._add_reference_file(str(path))

    assert dialog._file_message.isHidden()
    # The dialog assigns this same "file:1" id internally (its first open).
    document = load_reference_document(path.read_bytes(), path.name, "file:1")
    run = document.runs[0]
    assert run.id in dialog._picker_rows
    row = dialog._picker_rows[run.id]
    assert row._tick.isHidden()  # not added yet, just listed

    dialog._toggle_run(run)

    assert run.id in dialog._added
    assert run.id in dialog._chips
    assert not row._tick.isHidden()
    page = dialog._chart_page
    assert run.id in page.voltage._series
    assert dialog._chart_page.numbers.rowCount() == 1


def test_add_reference_file_with_no_validation_section_shows_a_message(tmp_path):
    payload = {"Header": {"Title": "No runs here"}}
    path = tmp_path / "empty.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    dialog = DatabaseExamplesDialog()
    dialog._add_reference_file(str(path))

    assert not dialog._file_message.isHidden()
    assert "empty.json" in dialog._file_message.text()
    assert "no validation runs" in dialog._file_message.text().lower()


def test_add_reference_file_with_invalid_json_surfaces_the_gateways_wording(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")

    dialog = DatabaseExamplesDialog()
    dialog._add_reference_file(str(path))

    assert not dialog._file_message.isHidden()
    # Verbatim gateway wording (see bpx_gateway.load_raw) -- this dialog
    # never rewords a decode failure.
    assert "not valid JSON" in dialog._file_message.text()
