"""ExperimentCard's Phase 3 additions: the import-first dropzone for an empty
run, the multi-column grid expand affordance, and the per-column sample-count
footer chip.

The dropzone empty state is a derived display fact, no new document state,
computed from the grid own column lengths, live (via changed) so a typed cell
dismisses it before any commit, and re-derived fresh whenever the card is
rebuilt (every commit rebuilds it; see InspectorPanel._show_experiment), so
undo naturally brings it back.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton

import ui_qt.cards.experiment as experiment_module

_RUN = ("Validation", "C/20 discharge")


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_exec_database_examples_dialog(monkeypatch):
    """``DatabaseExamplesDialog.exec()`` is a real blocking modal loop; every
    test that opens it here inspects the constructed instance directly
    instead -- the same non-blocking idiom ``test_database_examples_dialog.py``
    uses for the dialog's own tests (see ``AppDriver.open_database_examples_
    dialog_from_toolbar``)."""
    from ui_qt.cards.database_examples_dialog import DatabaseExamplesDialog

    monkeypatch.setattr(DatabaseExamplesDialog, "exec", lambda self: None)


def _write_doc(tmp_path, valid_spm_dict, validation, name="doc.json"):
    doc = dict(valid_spm_dict)
    doc["Validation"] = validation
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


class _StubCsvDialog:
    last = None

    def __init__(self, data, targets, parent=None, **kwargs):
        self.data = data
        self.targets = targets
        self.kwargs = kwargs
        self.accepted_mapping = None
        _StubCsvDialog.last = self

    def exec(self):
        pass


def _stub_dialog(monkeypatch, mapping):
    class _Configured(_StubCsvDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.accepted_mapping = mapping

    monkeypatch.setattr(experiment_module, "CsvImportDialog", _Configured)


def _stub_file_dialog(monkeypatch, path):
    monkeypatch.setattr(
        experiment_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


def test_freshly_created_empty_run_shows_the_dropzone(app_driver, tmp_path, valid_spm_dict):
    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))

    assert d.experiment_dropzone_shown() is True
    assert d.experiment_columns() == ("Time [s]", "Current [A]", "Voltage [V]")


def test_run_with_every_array_present_but_empty_shows_the_dropzone(
    app_driver, tmp_path, valid_spm_dict
):
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "New run": {
                "Time [s]": [],
                "Current [A]": [],
                "Voltage [V]": [],
                "Temperature [K]": [],
            }
        },
    )
    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))

    assert d.experiment_dropzone_shown() is True


def test_populated_run_never_shows_the_dropzone(app_driver, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)

    assert d.experiment_dropzone_shown() is False


def test_one_filled_column_is_enough_to_hide_the_dropzone(
    app_driver, tmp_path, valid_spm_dict
):
    workfile = _write_doc(tmp_path, valid_spm_dict, {"Partial": {"Time [s]": [0, 1, 2]}})
    d = app_driver
    d.open(workfile).go_to(("Validation", "Partial"))

    assert d.experiment_dropzone_shown() is False


def test_typing_the_first_value_dismisses_the_dropzone_live(
    app_driver, tmp_path, valid_spm_dict
):
    """A genuinely empty grid has zero displayed rows (see
    ``test_numeric_grid_multicolumn.test_row_count_is_zero_for_two_empty_columns``),
    so typing the very first value is, like any empty grid in this app, a
    "+" (create the row) then type the cell -- exactly what a real
    click on the grid's own "+" button does."""
    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))
    assert d.experiment_dropzone_shown() is True

    d.experiment_card()._grid.insert_cell()
    d.set_experiment_cell("Time [s]", 0, "0")

    assert d.experiment_dropzone_shown() is False
    assert d.undo_enabled() is False


def test_reverting_the_only_typed_value_brings_the_dropzone_back(
    app_driver, tmp_path, valid_spm_dict
):
    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))

    d.experiment_card()._grid.insert_cell()
    d.set_experiment_cell("Time [s]", 0, "0")
    assert d.experiment_dropzone_shown() is False

    d.revert_experiment()

    assert d.experiment_dropzone_shown() is True


def test_browse_import_fills_mapped_columns_in_one_undo_step_and_dismisses(
    app_driver, main_window, tmp_path, valid_spm_dict, monkeypatch
):
    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    csv_path = tmp_path / "trace.csv"
    csv_path.write_text("time,current,voltage\n0,-0.5,4.1\n50,-0.5,4.0\n", encoding="utf-8")
    _stub_file_dialog(monkeypatch, csv_path)
    _stub_dialog(monkeypatch, mapping=(0, 1, 2))

    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))
    assert d.experiment_dropzone_shown() is True

    d.click_experiment_dropzone_browse()

    run = main_window._state.active.document.raw["Validation"]["New run"]
    assert run["Time [s]"] == [0, 50]
    assert run["Current [A]"] == [-0.5, -0.5]
    assert run["Voltage [V]"] == [4.1, 4.0]
    assert d.undo_enabled() is True
    assert d.experiment_dropzone_shown() is False

    d.undo()

    assert main_window._state.active.document.raw["Validation"]["New run"] == {}
    assert d.experiment_dropzone_shown() is True


def test_dropped_file_fills_mapped_columns_the_same_way_as_browse(
    app_driver, main_window, tmp_path, valid_spm_dict, monkeypatch
):
    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    csv_path = tmp_path / "trace.csv"
    csv_path.write_text("time,current,voltage\n0,-0.5,4.1\n50,-0.5,4.0\n", encoding="utf-8")
    _stub_dialog(monkeypatch, mapping=(0, 1, 2))

    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))

    d.drop_file_on_experiment_dropzone(csv_path)

    run = main_window._state.active.document.raw["Validation"]["New run"]
    assert run["Time [s]"] == [0, 50]
    assert d.experiment_dropzone_shown() is False


def test_experiment_card_forwards_the_grids_expand_toggle(
    app_driver, spm_with_validation_path
):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)
    card = d.experiment_card()
    seen = []
    card.expand_toggled.connect(seen.append)

    card._grid._toggle_expanded()

    assert seen == [True]
    assert card._grid.is_expanded is True


def test_sample_count_chip_reports_each_columns_length(
    app_driver, spm_with_validation_path
):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)

    assert d.experiment_sample_count_text() == "Time 3 · Current 3 · Voltage 3 · Temperature 3"


def test_sample_count_chip_reflects_a_length_mismatch_factually(
    app_driver, tmp_path, valid_spm_dict
):
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "Ragged": {
                "Time [s]": [0, 1, 2, 3],
                "Current [A]": [-0.6, -0.6, -0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
            }
        },
    )
    d = app_driver
    d.open(workfile).go_to(("Validation", "Ragged"))

    assert d.experiment_sample_count_text() == "Time 4 · Current 4 · Voltage 2"


def test_sample_count_chip_updates_live_with_a_typed_value(
    app_driver, tmp_path, valid_spm_dict
):
    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))
    assert d.experiment_sample_count_text() == "Time 0 · Current 0 · Voltage 0"

    d.experiment_card()._grid.insert_cell()
    d.set_experiment_cell("Time [s]", 0, "0")

    assert d.experiment_sample_count_text() == "Time 1 · Current 0 · Voltage 0"


# ---------------------------------------------------------------------------
# "Compare…" entry point (toolbar-only -- redesign 2026-07-20 removed the
# dropzone's own affordance: getting data in is that widget's sole job now)
# ---------------------------------------------------------------------------


def test_dropzone_has_no_compare_or_database_examples_button(
    app_driver, tmp_path, valid_spm_dict
):
    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))
    assert d.experiment_dropzone_shown() is True

    dropzone = d.experiment_card()._dropzone
    assert dropzone.findChild(QPushButton, "ExperimentDropzoneDatabaseExamples") is None


def test_toolbar_compare_button_visible_while_the_dropzone_shows(
    app_driver, tmp_path, valid_spm_dict
):
    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))
    assert d.experiment_dropzone_shown() is True

    button = d.experiment_card()._database_examples_button
    assert button is not None and not button.isHidden()


def test_toolbar_compare_button_opens_dialog_with_no_you_series_on_an_empty_run(
    app_driver, tmp_path, valid_spm_dict
):
    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    d = app_driver
    d.open(workfile).go_to(("Validation", "New run"))

    dialog = d.open_database_examples_dialog_from_toolbar()

    assert dialog._added == {}
    assert not dialog._own_notice.isHidden()


def test_toolbar_compare_button_visible_in_both_empty_and_populated_states(
    app_driver, spm_with_validation_path, tmp_path, valid_spm_dict
):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)
    populated_button = d.experiment_card()._database_examples_button
    assert populated_button is not None and not populated_button.isHidden()

    workfile = _write_doc(tmp_path, valid_spm_dict, {"New run": {}})
    d.open(workfile).go_to(("Validation", "New run"))
    empty_button = d.experiment_card()._database_examples_button
    assert empty_button is not None and not empty_button.isHidden()


def test_toolbar_database_examples_labels_own_run_by_file_name_not_you(
    app_driver, spm_with_validation_path
):
    """The active document's own series reads "<file> · <run>" -- the file
    name, never "You" (Bella's call 2026-07-20). The fixture is saved as
    ``spm_with_validation.json``."""
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)

    dialog = d.open_database_examples_dialog_from_toolbar()

    assert "__you__" in dialog._added
    added = dialog._added["__you__"]
    assert added.label == "spm_with_validation · C/20 discharge"
    assert added.data == {
        "Time [s]": [0, 100, 200],
        "Current [A]": [-0.6, -0.6, -0.6],
        "Voltage [V]": [4.1, 4.0, 3.9],
        "Temperature [K]": [298.15, 298.15, 298.15],
    }


def test_toolbar_database_examples_labels_an_unsaved_document_active_file(
    app_driver, tmp_path, valid_spm_dict
):
    """An unsaved document has no real file name yet, so its own series falls
    back to "Active file · <run>" rather than a bare "untitled"."""
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {"C/20 discharge": {"Time [s]": [0, 1], "Current [A]": [-1, -1], "Voltage [V]": [4.0, 3.9]}},
        name="untitled.json",
    )
    d = app_driver
    d.open(workfile).go_to(_RUN)

    dialog = d.open_database_examples_dialog_from_toolbar()

    assert dialog._added["__you__"].label == "Active file · C/20 discharge"


def test_toolbar_database_examples_reflects_an_uncommitted_edit_live(
    app_driver, spm_with_validation_path
):
    """The own run is built from the grid's *current draft*, not the last
    commit -- an edit that has not been confirmed with Enter yet still shows
    up."""
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)
    d.set_experiment_cell("Voltage [V]", 0, "9.9")

    dialog = d.open_database_examples_dialog_from_toolbar()

    assert dialog._added["__you__"].data["Voltage [V]"] == [9.9, 4.0, 3.9]
