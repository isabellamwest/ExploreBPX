"""ExperimentCard: the unified editor for one Validation run.

Driven end to end through :class:`AppDriver` (a real ``MainWindow``, offscreen)
for everything routing/commit/undo-related -- the point of this phase is that
navigating anywhere under a Validation run now reaches one shared card, so the
navigation → Inspector → command → undo pipeline is exactly what needs
proving. ``read_only`` construction (nothing sets it ``True`` yet) is the one
case exercised by constructing the card directly against a real
:class:`~core.tree_model.TreeNode`.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui_qt.cards.experiment import ExperimentCard, KNOWN_ALIASES, is_validation_run_path

_RUN = ("Validation", "C/20 discharge")
_TIME = _RUN + ("Time [s]",)


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


def _write_doc(tmp_path, valid_spm_dict, validation: dict, name: str = "doc.json"):
    doc = dict(valid_spm_dict)
    doc["Validation"] = validation
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


# ----------------------------------------------------------------------
# is_validation_run_path: the shared predicate
# ----------------------------------------------------------------------


def test_is_validation_run_path_matches_only_a_run_node():
    assert is_validation_run_path(("Validation", "C/20 discharge")) is True
    assert is_validation_run_path(("Validation",)) is False
    assert is_validation_run_path(("Validation", "run", "Time [s]")) is False
    assert is_validation_run_path(("Header",)) is False


# ----------------------------------------------------------------------
# Routing: run-node vs. array vs. everything else
# ----------------------------------------------------------------------


def test_run_node_selection_shows_one_card_with_no_focused_column(
    app_driver, spm_with_validation_path
):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)

    assert d.experiment_columns() == KNOWN_ALIASES
    assert d.experiment_focused_column() is None


@pytest.mark.parametrize("alias", KNOWN_ALIASES)
def test_each_array_selection_shows_the_same_card_focused_on_itself(
    app_driver, spm_with_validation_path, alias
):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN + (alias,))

    assert d.experiment_columns() == KNOWN_ALIASES
    assert d.experiment_focused_column() == alias


def test_validation_container_selection_keeps_todays_placeholder(
    app_driver, spm_with_validation_path
):
    """Selecting the ``("Validation",)`` collection itself (not a run) is
    unaffected -- it carries no parameters of its own, exactly like today."""
    d = app_driver
    d.open(spm_with_validation_path).go_to(("Validation",))

    assert d.showing_placeholder() is True


def test_custom_field_under_a_run_keeps_its_own_single_parameter_card(
    app_driver, tmp_path, valid_spm_dict
):
    """Only a genuine array (SERIES kind) reroutes to ExperimentCard -- a
    custom, non-array field under a run is not one of ``KNOWN_ALIASES`` and
    keeps today's ordinary per-parameter card."""
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
                "Notes": "a custom field",
            }
        },
    )
    d = app_driver
    d.open(workfile).go_to(_RUN + ("Notes",))

    assert d.editor_kind() == "TextCard"


# ----------------------------------------------------------------------
# Commit path: a typed single-cell edit names only the changed column
# ----------------------------------------------------------------------


def test_single_cell_edit_commits_only_that_column(app_driver, main_window, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)

    d.set_experiment_cell("Time [s]", 1, "999")
    d.commit_experiment()

    assert d.experiment_column_values("Time [s]") == [0, 999, 200]
    assert d.experiment_column_values("Current [A]") == [-0.6, -0.6, -0.6]
    assert d.experiment_column_values("Voltage [V]") == [4.1, 4.0, 3.9]
    assert d.undo_enabled() is True

    run = main_window._state.active.document.raw["Validation"]["C/20 discharge"]
    assert run["Time [s]"] == [0, 999, 200]
    assert run["Current [A]"] == [-0.6, -0.6, -0.6]  # untouched columns not rewritten


def test_undo_reverts_only_the_edited_column(app_driver, main_window, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)

    d.set_experiment_cell("Time [s]", 1, "999").commit_experiment()
    d.undo()

    assert d.experiment_column_values("Time [s]") == [0, 100, 200]
    assert d.experiment_column_values("Current [A]") == [-0.6, -0.6, -0.6]
    assert d.undo_enabled() is False


def test_noop_enter_commits_nothing(app_driver, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)

    d.commit_experiment()

    assert d.undo_enabled() is False


def test_escape_reverts_every_edited_column(app_driver, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)

    d.set_experiment_cell("Time [s]", 0, "999")
    d.set_experiment_cell("Voltage [V]", 0, "1.0")
    assert d.experiment_column_values("Time [s]") == [999, 100, 200]

    d.revert_experiment()

    assert d.experiment_column_values("Time [s]") == [0, 100, 200]
    assert d.experiment_column_values("Voltage [V]") == [4.1, 4.0, 3.9]
    assert d.undo_enabled() is False


def test_enter_inside_a_cell_editor_confirms_the_cell_not_the_document(
    app_driver, spm_with_validation_path
):
    """The two keyboard layers must not collide: Enter in an open cell editor
    confirms that cell (Qt's delegate) and must NOT commit the document --
    exactly the guarantee ``test_workflows_ui.py`` used to pin against
    ``SeriesCard``, now proven against the card that actually shows here."""
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)

    d.open_experiment_cell_editor("Time [s]", 0)
    assert d.experiment_cell_editor_open() is True

    d.press_in_experiment_cell_editor(Qt.Key_Return)

    assert d.experiment_cell_editor_open() is False
    assert d.experiment_column_values("Time [s]")[0] == 1  # the digit that opened it
    assert d.undo_enabled() is False  # nothing reached the document


def test_escape_inside_a_cell_editor_cancels_the_cell_not_the_card(
    app_driver, spm_with_validation_path
):
    """Escape in an open cell editor cancels that cell only; a separate draft
    in another cell survives (it does not reach the card's grid-level revert)."""
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)

    d.set_experiment_cell("Time [s]", 1, "555")  # a standing draft elsewhere
    d.open_experiment_cell_editor("Time [s]", 0)
    assert d.experiment_cell_editor_open() is True

    d.press_in_experiment_cell_editor(Qt.Key_Escape)

    assert d.experiment_cell_editor_open() is False
    assert d.experiment_column_values("Time [s]") == [0, 555, 200]  # row 0 unchanged, 1 kept


def test_editing_two_columns_commits_both_in_one_undo_step(
    app_driver, main_window, spm_with_validation_path
):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)

    d.set_experiment_cell("Time [s]", 0, "999")
    d.set_experiment_cell("Voltage [V]", 0, "1.0")
    d.commit_experiment()

    assert d.experiment_column_values("Time [s]") == [999, 100, 200]
    assert d.experiment_column_values("Voltage [V]") == [1.0, 4.0, 3.9]

    d.undo()

    assert d.experiment_column_values("Time [s]") == [0, 100, 200]
    assert d.experiment_column_values("Voltage [V]") == [4.1, 4.0, 3.9]


# ----------------------------------------------------------------------
# Ragged columns: independent lengths, never padded
# ----------------------------------------------------------------------


def test_length_mismatch_renders_each_columns_true_length(
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
                "Temperature [K]": [298.15, 298.15, 298.15, 298.15],
            }
        },
    )
    d = app_driver
    d.open(workfile).go_to(("Validation", "Ragged"))

    assert d.experiment_column_values("Time [s]") == [0, 1, 2, 3]
    assert d.experiment_column_values("Voltage [V]") == [4.1, 4.0]  # not padded

    card = d.experiment_card()
    assert card._grid.column_length(0) == 4
    assert card._grid.column_length(2) == 2
    assert card._grid._model.rowCount() == 4  # the longest column


def test_no_length_mismatch_chip_without_a_bpx_diagnostic(
    app_driver, tmp_path, valid_spm_dict
):
    """``bpx.schema.Experiment`` has no cross-array length check at all
    (verified directly against the installed schema) -- so even genuinely
    ragged arrays draw no chip today. This pins that fact: the chip mechanism
    reuses whatever diagnostics the run's own node/columns already carry and
    never computes a mismatch itself, so if a future bpx version adds a real
    check, this test (not new card logic) is what needs revisiting."""
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "Ragged": {
                "Time [s]": [0, 1, 2, 3],
                "Current [A]": [-0.6, -0.6, -0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
                "Temperature [K]": [298.15, 298.15, 298.15, 298.15],
            }
        },
    )
    d = app_driver
    d.open(workfile).go_to(("Validation", "Ragged"))

    assert d.experiment_chip_text() is None


# ----------------------------------------------------------------------
# Diagnostics: a bad element tints the right column via experiment_cells
# ----------------------------------------------------------------------


def test_diagnostic_on_an_array_tints_its_own_column(app_driver, tmp_path, valid_spm_dict):
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100, 200],
                "Current [A]": [-0.6, -0.6, -0.6],
                "Voltage [V]": [4.1, "oops", 3.9],
                "Temperature [K]": [298.15, 298.15, 298.15],
            }
        },
    )
    d = app_driver
    d.open(workfile).go_to(_RUN)

    assert d.experiment_cell_tooltip("Voltage [V]", 1)
    assert d.experiment_cell_tooltip("Time [s]", 1) is None
    assert d.experiment_cell_tooltip("Voltage [V]", 0) is None


# ----------------------------------------------------------------------
# CSV import: one atomic SetValues across every mapped column
# ----------------------------------------------------------------------


def test_csv_import_fills_all_mapped_columns_in_one_undo_step(
    app_driver, main_window, spm_with_validation_path
):
    from core.csv_import import read_csv_text

    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)

    data = read_csv_text(
        "time,current,voltage,temp\n0,-0.5,4.1,298.15\n50,-0.5,4.0,298.15\n"
    )
    d.experiment_import_csv(data, (0, 1, 2, 3))

    run = main_window._state.active.document.raw["Validation"]["C/20 discharge"]
    assert run["Time [s]"] == [0, 50]
    assert run["Current [A]"] == [-0.5, -0.5]
    assert run["Voltage [V]"] == [4.1, 4.0]
    assert run["Temperature [K]"] == [298.15, 298.15]
    assert d.undo_enabled() is True

    d.undo()

    run = main_window._state.active.document.raw["Validation"]["C/20 discharge"]
    assert run["Time [s]"] == [0, 100, 200]  # one undo step restored every column
    assert run["Temperature [K]"] == [298.15, 298.15, 298.15]


# ----------------------------------------------------------------------
# "+ Temperature [K]": appears only while absent
# ----------------------------------------------------------------------


def test_add_temperature_button_appears_only_when_absent(
    app_driver, main_window, tmp_path, valid_spm_dict
):
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "No temp": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
            }
        },
    )
    d = app_driver
    d.open(workfile).go_to(("Validation", "No temp"))

    assert d.experiment_columns() == ("Time [s]", "Current [A]", "Voltage [V]")
    assert d.experiment_add_temperature_button() is not None

    d.click_experiment_add_temperature()

    assert d.experiment_columns() == KNOWN_ALIASES
    assert d.experiment_column_values("Temperature [K]") == []
    assert d.experiment_add_temperature_button() is None
    run = main_window._state.active.document.raw["Validation"]["No temp"]
    assert run["Temperature [K]"] == []


def test_add_temperature_button_absent_when_already_present(
    app_driver, spm_with_validation_path
):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)

    assert d.experiment_add_temperature_button() is None


# ----------------------------------------------------------------------
# Paths never cached: a rename while the card is open stays fresh
# ----------------------------------------------------------------------


def test_rename_while_open_keeps_the_card_fresh(app_driver, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)
    assert d.experiment_card().run_path == _RUN

    d.rename_node(_RUN, "Renamed run")

    card = d.experiment_card()
    assert card.run_path == ("Validation", "Renamed run")
    assert d.experiment_title() == "Experiment · Renamed run"
    assert d.experiment_column_values("Time [s]") == [0, 100, 200]


# ----------------------------------------------------------------------
# read_only: nothing sets this True yet, so it is exercised directly
# ----------------------------------------------------------------------


def _run_node(raw: dict, run_name: str = "C/20 discharge"):
    from core.document import BPXDocument

    document = BPXDocument.from_raw(raw, filename="probe.json", fmt="json")
    return document.find(("Validation", run_name))


def test_read_only_construction_blocks_edits(valid_spm_dict):
    doc = dict(valid_spm_dict)
    doc["Validation"] = {
        "C/20 discharge": {
            "Time [s]": [0, 100, 200],
            "Current [A]": [-0.6, -0.6, -0.6],
            "Voltage [V]": [4.1, 4.0, 3.9],
            "Temperature [K]": [298.15, 298.15, 298.15],
        }
    }
    run = _run_node(doc)

    card = ExperimentCard(run, read_only=True)

    assert card._import_button is None
    assert card._add_temperature_button is None
    model = card._grid._model
    assert not model.flags(model.index(0, 0)) & Qt.ItemIsEditable
    assert model.setData(model.index(0, 0), "999", Qt.EditRole) is False
    assert card.is_dirty is False


# ----------------------------------------------------------------------
# CSV import: targets and feedback
# ----------------------------------------------------------------------


_PLAIN_RUN = {
    "Time [s]": [0, 1],
    "Current [A]": [-1.0, -1.0],
    "Voltage [V]": [4.0, 3.9],
}


def test_csv_targets_offer_temperature_before_the_column_exists(valid_spm_dict):
    """A 4-column CSV must be mappable from the card's own import too --
    the empty state's flow always offered all four aliases, while this
    card's used to silently drop Temperature whenever the column was
    absent. Two entry points, one outcome."""
    doc = dict(valid_spm_dict)
    doc["Validation"] = {"C/20 discharge": dict(_PLAIN_RUN)}
    card = ExperimentCard(_run_node(doc))

    targets = card._csv_targets()

    assert tuple(label for label, _ in targets) == KNOWN_ALIASES
    assert dict(targets)["Temperature [K]"] == (
        "Validation",
        "C/20 discharge",
        "Temperature [K]",
    )


def test_unreadable_and_empty_csv_show_a_message_instead_of_doing_nothing(
    valid_spm_dict, monkeypatch
):
    from types import SimpleNamespace

    from ui_qt.cards import experiment as experiment_module

    doc = dict(valid_spm_dict)
    doc["Validation"] = {"C/20 discharge": dict(_PLAIN_RUN)}
    card = ExperimentCard(_run_node(doc))
    assert card._import_message.isHidden()

    def raise_oserror(_path):
        raise OSError("locked")

    monkeypatch.setattr(experiment_module, "read_csv_file", raise_oserror)
    card._import_csv_from_path("C:/somewhere/data.csv")
    assert not card._import_message.isHidden()
    assert "data.csv" in card._import_message.text()

    monkeypatch.setattr(
        experiment_module, "read_csv_file", lambda _path: SimpleNamespace(row_count=0)
    )
    card._import_csv_from_path("C:/somewhere/empty.csv")
    assert not card._import_message.isHidden()
    assert "empty.csv" in card._import_message.text()
    assert "no data rows" in card._import_message.text()


def test_import_button_is_disabled_not_hidden_while_the_run_is_empty(valid_spm_dict):
    """Disabling keeps the header row stable: hiding made "Compare…" jump
    sideways the moment a first cell was typed."""
    doc = dict(valid_spm_dict)
    doc["Validation"] = {"C/20 discharge": {}}
    card = ExperimentCard(_run_node(doc))
    assert card._import_button.isEnabled() is False

    doc = dict(valid_spm_dict)
    doc["Validation"] = {"C/20 discharge": dict(_PLAIN_RUN)}
    card = ExperimentCard(_run_node(doc))
    assert card._import_button.isEnabled() is True
