"""CSV import: file parsing, auto-mapping, the mapping dialog's gate, and the
atomic write path.

The pure layer (``csv_import.py``) carries the parsing/mapping logic; the
dialog is exercised directly (constructed, not ``exec``'d); the write path is
tested from the card's ``_apply_csv_import`` down through the Inspector to the
document, which is where a half-applied import would silently desynchronise a
run's arrays.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, SiblingSeries
from ui_qt.cards.csv_import import CsvData, auto_map, read_csv_text

_TARGETS = ("Time [s]", "Current [A]", "Voltage [V]", "Temperature [K]")


# ----------------------------------------------------------------------
# read_csv_text: delimiters, headers, raw cells
# ----------------------------------------------------------------------


def test_reads_comma_csv_with_header():
    data = read_csv_text("time (s),current (A)\n0,-0.6\n100,-0.5\n")
    assert data.delimiter == "comma"
    assert data.headers == ("time (s)", "current (A)")
    assert data.columns == ((0, 100), (-0.6, -0.5))
    assert data.rejected == 0


def test_reads_semicolon_csv():
    data = read_csv_text("0;1\n2;3\n")
    assert data.delimiter == "semicolon"
    assert data.headers is None  # numeric first row is data, not a header
    assert data.columns == ((0, 2), (1, 3))


def test_reads_whitespace_columns_via_fallback():
    """The csv sniffer cannot classify space-aligned columns; the clipboard
    parser's delimiter detection takes over so a .txt export still imports."""
    data = read_csv_text("0 4.1\n100 4.0\n")
    assert data.columns == ((0, 100), (4.1, 4.0))


def test_quoted_field_with_embedded_comma_is_one_cell():
    data = read_csv_text('name,value\n"a, b",5\n')
    assert data.columns[0] == ("a, b",)
    assert data.columns[1] == (5,)


def test_short_row_pads_with_none_never_zero():
    data = read_csv_text("t,v\n0,4.1\n100\n")
    assert data.columns == ((0, 100), (4.1, None))


def test_non_numeric_cell_kept_as_text_and_counted():
    data = read_csv_text("t,v\n0,oops\n")
    assert data.columns[1] == ("oops",)
    assert data.rejected == 1


def test_empty_text_is_zero_rows():
    data = read_csv_text("  \n\n")
    assert data.row_count == 0
    assert data.column_count == 0


def test_column_names_fall_back_to_numbering():
    data = read_csv_text("0,1\n")
    assert data.column_name(0) == "Column 1"
    assert data.column_name(1) == "Column 2"


# ----------------------------------------------------------------------
# auto_map: a proposal, matched by normalised name or by position
# ----------------------------------------------------------------------


def test_auto_map_matches_headers_ignoring_units_and_case():
    data = read_csv_text("Temp (K),time (s),voltage (V),Current\n1,2,3,4\n")
    assert auto_map(data, _TARGETS) == (1, 3, 2, 0)


def test_auto_map_leaves_unrecognised_targets_unmapped():
    data = read_csv_text("time,frequency\n1,2\n")
    assert auto_map(data, _TARGETS) == (0, None, None, None)


def test_auto_map_uses_each_column_once():
    data = read_csv_text("time,time\n1,2\n")
    assert auto_map(data, ("Time [s]", "Time [s]")) == (0, 1)


def test_auto_map_without_headers_is_positional():
    data = read_csv_text("0,1,2\n3,4,5\n")
    assert auto_map(data, _TARGETS) == (0, 1, 2, None)


# ----------------------------------------------------------------------
# CsvImportDialog: always-editable mapping, blocked with a reason
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _dialog(text="time,voltage\n0,4.1\n100,4.0\n", targets=("Time [s]", "Voltage [V]")):
    from ui_qt.cards.csv_dialog import CsvImportDialog

    return CsvImportDialog(read_csv_text(text), targets)


def test_dialog_preselects_the_auto_map():
    dialog = _dialog()
    assert dialog.mapping() == (0, 1)
    assert dialog._import_button.isEnabled()
    assert not dialog._reason.isVisible()


def test_dialog_blocks_a_duplicate_column_with_a_reason():
    dialog = _dialog()
    dialog._combos[1].setCurrentIndex(1)  # both targets -> file column 0
    assert dialog._import_button.isEnabled() is False
    assert "one parameter" in dialog._reason.text()


def test_dialog_blocks_an_all_skip_mapping():
    dialog = _dialog()
    for combo in dialog._combos:
        combo.setCurrentIndex(0)  # skip
    assert dialog._import_button.isEnabled() is False
    assert "at least one" in dialog._reason.text()


def test_dialog_confirms_the_edited_mapping():
    dialog = _dialog()
    dialog._combos[1].setCurrentIndex(0)  # skip Voltage
    dialog._choose()
    assert dialog.accepted_mapping == (0, None)


def test_dialog_cancel_leaves_no_mapping():
    dialog = _dialog()
    dialog.reject()
    assert dialog.accepted_mapping is None


# ----------------------------------------------------------------------
# SeriesCard: the write path (one atomic SetValues; skips never blank)
# ----------------------------------------------------------------------


def _validation_card():
    from ui_qt.cards.registry import create_card

    run = ("Validation", "C/20 discharge")
    param = ParameterItem(
        label="Time [s]",
        path=run + ("Time [s]",),
        kind=ParameterKind.SERIES,
        value=[0, 100],
        sibling_series=(
            SiblingSeries("Current [A]", run + ("Current [A]",), [-0.6, -0.6]),
            SiblingSeries("Voltage [V]", run + ("Voltage [V]",), [4.1, 4.0]),
            SiblingSeries("Temperature [K]", run + ("Temperature [K]",), [298.15, 298.15]),
        ),
    )
    return create_card(param, None)


def test_import_button_appears_only_in_the_expanded_editor():
    card = _validation_card()
    assert card._import_button.isHidden()
    card._grid._toggle_expanded()
    assert not card._import_button.isHidden()
    card._grid._toggle_expanded()
    assert card._import_button.isHidden()


def test_apply_csv_import_emits_one_setvalues_own_parameter_first():
    from core.commands import SetValues

    card = _validation_card()
    emitted = []
    card.bulk_commit_requested.connect(emitted.append)
    data = read_csv_text("time,current,voltage,temp\n0,-0.5,4.1,298.15\n50,-0.5,4.0,298.15\n")
    card._apply_csv_import(data, (0, 1, 2, 3))

    assert len(emitted) == 1
    command = emitted[0]
    assert isinstance(command, SetValues)
    assert command.label == "Import CSV"
    assert command.updates == (
        (("Validation", "C/20 discharge", "Time [s]"), [0, 50]),
        (("Validation", "C/20 discharge", "Current [A]"), [-0.5, -0.5]),
        (("Validation", "C/20 discharge", "Voltage [V]"), [4.1, 4.0]),
        (("Validation", "C/20 discharge", "Temperature [K]"), [298.15, 298.15]),
    )


def test_apply_csv_import_skipped_target_is_not_touched():
    card = _validation_card()
    emitted = []
    card.bulk_commit_requested.connect(emitted.append)
    data = read_csv_text("time,voltage\n0,4.1\n")
    card._apply_csv_import(data, (0, None, 1, None))

    paths = [path for path, _ in emitted[0].updates]
    assert ("Validation", "C/20 discharge", "Current [A]") not in paths
    assert ("Validation", "C/20 discharge", "Temperature [K]") not in paths


def test_apply_csv_import_with_nothing_mapped_emits_nothing():
    card = _validation_card()
    emitted = []
    card.bulk_commit_requested.connect(emitted.append)
    card._apply_csv_import(read_csv_text("0,1\n"), (None, None, None, None))
    assert emitted == []


# ----------------------------------------------------------------------
# End to end: card -> Inspector -> session -> document, one undo step
# ----------------------------------------------------------------------


def test_bulk_commit_reaches_the_document_and_undoes_as_one_step(
    qtbot, spm_with_validation_path
):
    from state.app_state import AppState
    from ui_qt.inspector import InspectorPanel

    state = AppState()
    state.open(spm_with_validation_path)
    session = state.active
    time_path = ("Validation", "C/20 discharge", "Time [s]")
    session.select(time_path[:-1])
    session.select_parameter(time_path)

    panel = InspectorPanel(state)
    qtbot.addWidget(panel)
    panel.show_parameter(session.selected_parameter())

    data = read_csv_text(
        "time,current,voltage,temp\n0,-0.5,4.1,298.15\n50,-0.5,4.0,298.15\n"
    )
    before = session.document.raw["Validation"]["C/20 discharge"]
    panel._card._editor._apply_csv_import(data, (0, 1, 2, 3))

    run = session.document.raw["Validation"]["C/20 discharge"]
    assert run["Time [s]"] == [0, 50]
    assert run["Current [A]"] == [-0.5, -0.5]
    assert run["Voltage [V]"] == [4.1, 4.0]
    assert run["Temperature [K]"] == [298.15, 298.15]
    assert session.dirty

    session.undo()
    assert session.document.raw["Validation"]["C/20 discharge"] == before
