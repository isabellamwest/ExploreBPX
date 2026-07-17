"""DatabaseExamplesDialog: read-only comparison viewer over bundled examples.

Constructed directly and inspected, never through ``.exec()`` -- this is a
disposable viewer with nothing to confirm back to a caller, so there is
nothing gained by opening a real blocking modal loop just to test it (the
non-blocking idiom the feature's own spec calls for).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from core.example_library import ExampleRun, list_example_runs
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


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


def _first_run() -> ExampleRun:
    return list_example_runs()[0]


def test_with_no_own_run_nothing_is_added_and_the_hint_shows():
    dialog = DatabaseExamplesDialog()

    assert dialog._added == {}
    assert dialog._view_stack.currentWidget() is dialog._hint_label


def test_own_run_is_added_first_in_accent_and_never_takes_a_reference_slot():
    dialog = DatabaseExamplesDialog(_OWN_RUN, "You — test run")

    assert list(dialog._added) == ["__you__"]
    added = dialog._added["__you__"]
    assert added.color == ACCENT
    assert added.label == "You — test run"
    assert dialog._reference_slots == [None] * MAX_REFERENCE_RUNS


def test_adding_a_reference_run_gets_the_first_palette_colour_and_a_chip():
    dialog = DatabaseExamplesDialog()
    run = _first_run()

    dialog._toggle_run(run)

    assert dialog._added[run.id].color == "#008300"
    assert run.id in dialog._chips
    assert dialog._chips[run.id].color == "#008300"
    # The toggle control on the left picker reflects "added" too.
    assert dialog._toggle_buttons[run.id].text() == "✓"


def test_adding_a_reference_run_adds_its_curve_to_every_relevant_chart():
    dialog = DatabaseExamplesDialog()
    run = _first_run()

    dialog._toggle_run(run)

    page = dialog._chart_page
    assert run.id in page.voltage._series
    assert run.id in page.current._series
    assert run.id in page.temperature._series  # every bundled run has one


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
    assert dialog._toggle_buttons[run.id].text() == "+"


def test_removing_a_run_frees_its_colour_slot_for_the_next_add():
    dialog = DatabaseExamplesDialog()
    runs = list_example_runs()

    dialog._toggle_run(runs[0])
    assert dialog._added[runs[0].id].color == "#008300"

    dialog._remove_series(runs[0].id)
    dialog._toggle_run(runs[1])

    assert dialog._added[runs[1].id].color == "#008300"


def test_a_fifth_reference_run_is_refused(monkeypatch):
    """The real catalog has only four runs today, so a fifth distinct id is
    synthesised here to actually exercise the refusal path end to end."""
    real_runs = list(list_example_runs())
    extra = ExampleRun(
        id="bpx_official/nmc_pouch_cell_BPX::extra run",
        document_id="bpx_official/nmc_pouch_cell_BPX",
        document_title=real_runs[0].document_title,
        short_title=real_runs[0].short_title,
        model=real_runs[0].model,
        run_name="extra run",
        point_count=real_runs[0].point_count,
        has_temperature=real_runs[0].has_temperature,
    )
    monkeypatch.setattr(dialog_module, "list_example_runs", lambda: (*real_runs, extra))
    monkeypatch.setattr(
        dialog_module, "load_example_run", lambda run_id: dict(_OWN_RUN)
    )

    dialog = DatabaseExamplesDialog()
    five_runs = list(dialog_module.list_example_runs())
    assert len(five_runs) == 5

    for run in five_runs[:MAX_REFERENCE_RUNS]:
        dialog._toggle_run(run)
    assert dialog._cap_message.isHidden()

    dialog._toggle_run(five_runs[4])

    assert five_runs[4].id not in dialog._added
    assert not dialog._cap_message.isHidden()
    assert "4" in dialog._cap_message.text() or str(MAX_REFERENCE_RUNS) in dialog._cap_message.text()


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


def test_table_shows_the_selected_series_full_data_including_temperature():
    dialog = DatabaseExamplesDialog()
    run = _first_run()
    dialog._toggle_run(run)
    dialog._on_mode_clicked(1)

    headers = [
        dialog._table.horizontalHeaderItem(c).text() for c in range(dialog._table.columnCount())
    ]
    assert headers == ["Time [s]", "Current [A]", "Voltage [V]", "Temperature [K]"]

    from core.example_library import load_example_run

    data = load_example_run(run.id)
    assert dialog._table.rowCount() == len(data["Time [s]"])
    assert dialog._table.item(0, 0).text() == str(data["Time [s]"][0])
    assert dialog._table.item(0, 3).text() == str(data["Temperature [K]"][0])


def test_temperature_panel_hidden_until_a_series_with_temperature_is_added():
    dialog = DatabaseExamplesDialog(_OWN_RUN)  # "You" has no Temperature

    assert dialog._chart_page.temperature.isHidden()

    dialog._toggle_run(_first_run())  # every bundled run has one

    assert not dialog._chart_page.temperature.isHidden()

    dialog._remove_series(_first_run().id)

    assert dialog._chart_page.temperature.isHidden()


def test_you_can_be_removed_via_its_own_chip_without_crashing():
    """"You" is a chip like any other -- its "x" must not assume it occupies
    a reference colour slot (it never does)."""
    dialog = DatabaseExamplesDialog(_OWN_RUN, "You")

    dialog._remove_series("__you__")

    assert dialog._added == {}
    assert dialog._selected_table_id is None
    assert dialog._view_stack.currentWidget() is dialog._hint_label


def test_you_carries_line_width_three_and_reference_runs_carry_two():
    dialog = DatabaseExamplesDialog(_OWN_RUN)
    run = _first_run()
    dialog._toggle_run(run)

    you_line = dialog._chart_page.voltage._series["__you__"]
    run_line = dialog._chart_page.voltage._series[run.id]
    assert you_line.pen().widthF() == 3.0
    assert run_line.pen().widthF() == 2.0
