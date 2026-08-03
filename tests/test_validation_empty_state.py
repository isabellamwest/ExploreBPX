"""ValidationEmptyState (Phase 4): the guided empty state for a zero-run
Validation section.

Driven end to end through AppDriver (a real MainWindow, offscreen), like
test_experiment_card.py: the point is the whole reveal -> click -> command ->
undo -> reveal-again pipeline, not just the widget in isolation.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

import ui_qt.validation_empty_state as empty_state_module


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def spm_with_empty_validation_path(valid_spm_dict, tmp_path):
    doc = dict(valid_spm_dict)
    doc["Validation"] = {}
    work = tmp_path / "empty_validation.json"
    work.write_text(json.dumps(doc), encoding="utf-8")
    return work


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

    monkeypatch.setattr(empty_state_module, "CsvImportDialog", _Configured)


def _stub_cancelled_dialog(monkeypatch):
    monkeypatch.setattr(empty_state_module, "CsvImportDialog", _StubCsvDialog)


def _stub_file_dialog(monkeypatch, path):
    monkeypatch.setattr(
        empty_state_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


def _stub_no_file_chosen(monkeypatch):
    monkeypatch.setattr(
        empty_state_module.QFileDialog, "getOpenFileName", lambda *a, **k: ("", "")
    )


# ----------------------------------------------------------------------
# Selection: the guided empty state only for zero runs
# ----------------------------------------------------------------------


def test_zero_run_container_shows_the_guided_empty_state(
    app_driver, spm_with_empty_validation_path
):
    d = app_driver
    d.open(spm_with_empty_validation_path).go_to(("Validation",))

    assert d.validation_empty_state_shown() is True
    assert d.showing_placeholder() is False
    widget = d._validation_empty_state()
    assert widget._add_button.text() == "+ Add experiment"
    assert widget._import_button.text() == "Import CSV…"


def test_container_with_a_run_keeps_todays_placeholder(
    app_driver, spm_with_validation_path
):
    d = app_driver
    d.open(spm_with_validation_path).go_to(("Validation",))

    assert d.validation_empty_state_shown() is False
    assert d.showing_placeholder() is True


# ----------------------------------------------------------------------
# "+ Add experiment": one AddSection undo step, lands on the new run's card
# ----------------------------------------------------------------------


def test_add_experiment_creates_a_run_and_reveals_its_card(
    app_driver, main_window, spm_with_empty_validation_path
):
    d = app_driver
    d.open(spm_with_empty_validation_path).go_to(("Validation",))

    d.click_add_experiment()
    d.confirm_validation_empty_state_name("1C discharge")

    assert main_window._state.active.document.raw["Validation"]["1C discharge"] == {}
    assert d.undo_enabled() is True
    # The Inspector lands on the new (empty) run's card -- a brand-new run
    # has none of its four keys yet, so this is the Phase 3 dropzone card.
    assert d.experiment_dropzone_shown() is True
    assert d.experiment_card().run_path == ("Validation", "1C discharge")


def test_empty_state_disappears_once_a_run_exists(
    app_driver, spm_with_empty_validation_path
):
    d = app_driver
    d.open(spm_with_empty_validation_path).go_to(("Validation",))
    d.click_add_experiment()
    d.confirm_validation_empty_state_name("1C discharge")

    d.go_to(("Validation",))

    assert d.validation_empty_state_shown() is False
    assert d.showing_placeholder() is True


def test_add_experiment_undo_removes_the_run(
    app_driver, main_window, spm_with_empty_validation_path
):
    d = app_driver
    d.open(spm_with_empty_validation_path).go_to(("Validation",))
    d.click_add_experiment()
    d.confirm_validation_empty_state_name("1C discharge")

    d.undo()

    assert main_window._state.active.document.raw["Validation"] == {}
    assert d.validation_empty_state_shown() is True


# ----------------------------------------------------------------------
# "Import CSV as new experiment...": exactly two undo steps
# ----------------------------------------------------------------------


def test_import_csv_as_new_experiment_creates_and_fills_in_two_undo_steps(
    app_driver, main_window, tmp_path, spm_with_empty_validation_path, monkeypatch
):
    csv_path = tmp_path / "trace.csv"
    csv_path.write_text("time,current,voltage\n0,-0.5,4.1\n50,-0.5,4.0\n", encoding="utf-8")
    _stub_file_dialog(monkeypatch, csv_path)
    _stub_dialog(monkeypatch, mapping=(0, 1, 2, None))

    d = app_driver
    d.open(spm_with_empty_validation_path).go_to(("Validation",))

    d.click_import_csv_as_new_experiment()
    d.confirm_validation_empty_state_name("1C discharge")

    run = main_window._state.active.document.raw["Validation"]["1C discharge"]
    assert run["Time [s]"] == [0, 50]
    assert run["Current [A]"] == [-0.5, -0.5]
    assert run["Voltage [V]"] == [4.1, 4.0]
    assert d.undo_enabled() is True

    d.undo()  # first undo: only the fill reverts

    assert main_window._state.active.document.raw["Validation"]["1C discharge"] == {}
    assert d.undo_enabled() is True  # the "add run" step is still there to undo

    d.undo()  # second undo: the run itself goes away

    assert main_window._state.active.document.raw["Validation"] == {}
    assert d.undo_enabled() is False


def test_import_csv_cancelled_mapping_creates_nothing(
    app_driver, main_window, tmp_path, spm_with_empty_validation_path, monkeypatch
):
    csv_path = tmp_path / "trace.csv"
    csv_path.write_text("time,current,voltage\n0,-0.5,4.1\n", encoding="utf-8")
    _stub_file_dialog(monkeypatch, csv_path)
    _stub_cancelled_dialog(monkeypatch)

    d = app_driver
    d.open(spm_with_empty_validation_path).go_to(("Validation",))

    d.click_import_csv_as_new_experiment()
    d.confirm_validation_empty_state_name("1C discharge")

    assert main_window._state.active.document.raw["Validation"] == {}
    assert d.undo_enabled() is False
    assert d.validation_empty_state_shown() is True


def test_import_csv_no_file_chosen_is_a_noop(
    app_driver, main_window, spm_with_empty_validation_path, monkeypatch
):
    _stub_no_file_chosen(monkeypatch)

    d = app_driver
    d.open(spm_with_empty_validation_path).go_to(("Validation",))

    d.click_import_csv_as_new_experiment()

    assert main_window._state.active.document.raw["Validation"] == {}
    assert d.undo_enabled() is False
    assert d.validation_empty_state_shown() is True
