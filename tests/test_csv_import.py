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

from core.csv_import import (
    CsvData,
    auto_map,
    positional_map,
    read_csv_file,
    read_csv_text,
)
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, SiblingSeries

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
# read_csv_file: the BOM-tolerant, shared file read
# ----------------------------------------------------------------------


def test_read_csv_file_is_bom_tolerant(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes("time,value\n0,1\n100,2\n".encode("utf-8-sig"))

    data = read_csv_file(path)

    assert data.headers == ("time", "value")
    assert data.columns == ((0, 100), (1, 2))


def test_read_csv_file_replaces_undecodable_bytes_rather_than_raising(tmp_path):
    """A byte that is not UTF-8 must not abort the import -- it survives as a
    visible replacement character (kept as text), same as any other cell the
    parser cannot read as a number."""
    path = tmp_path / "bad_bytes.csv"
    path.write_bytes(b"name,value\n\xffoops,5\n")

    data = read_csv_file(path)

    assert data.rejected == 1
    assert isinstance(data.columns[0][0], str)


# ----------------------------------------------------------------------
# auto_map / positional_map: a proposal, matched by normalised name or by
# position
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


def test_positional_map_proposes_column_n_for_target_n():
    assert positional_map(3, 3) == (0, 1, 2)


def test_positional_map_is_none_for_targets_past_the_files_width():
    """Fewer file columns than targets: the rest are unmapped, not invented."""
    assert positional_map(2, 4) == (0, 1, None, None)


def test_positional_map_is_what_auto_map_uses_without_headers():
    data = read_csv_text("0,1,2\n3,4,5\n")
    assert auto_map(data, _TARGETS) == positional_map(data.column_count, len(_TARGETS))


# ----------------------------------------------------------------------
# CsvImportDialog: always-editable mapping, blocked with a reason
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _dialog(text="time,voltage\n0,4.1\n100,4.0\n", targets=("Time [s]", "Voltage [V]"), **kwargs):
    from ui_qt.cards.csv_dialog import CsvImportDialog

    return CsvImportDialog(read_csv_text(text), targets, **kwargs)


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
# CsvImportDialog: the three optional table-import parameters
# ----------------------------------------------------------------------


def test_dialog_proposed_overrides_the_auto_map():
    """A hostile header: "y" is a substring of "capacity", so on this file
    ``auto_map(("x", "y"))`` proposes ``(None, 0)`` -- y filled from the x
    column, x left unmapped. An explicit ``proposed`` (the table's
    positional_map) is what the dialog actually preselects, overriding that
    wrong guess entirely rather than merely coinciding with it."""
    text = "Capacity,Voltage\n0,1\n2,3\n"
    assert auto_map(read_csv_text(text), ("x", "y")) == (None, 0)  # sanity check
    dialog = _dialog(text=text, targets=("x", "y"), proposed=(0, 1))
    assert dialog.mapping() == (0, 1)


def test_dialog_require_all_targets_blocks_when_only_one_is_mapped():
    dialog = _dialog(
        text="x,y\n0,1\n2,3\n", targets=("x", "y"), require_all_targets=True
    )
    assert dialog.mapping() == (0, 1)  # both auto-mapped to start
    dialog._combos[1].setCurrentIndex(0)  # skip y

    assert dialog._import_button.isEnabled() is False
    assert "x and y" in dialog._reason.text()


def test_dialog_require_all_targets_names_the_files_column_shortfall():
    """A one-column file cannot fill two required targets: telling the user to
    "choose a column for x and y" is not actionable when there simply isn't a
    second column, so the reason instead says what is actually wrong."""
    dialog = _dialog(text="0\n1\n", targets=("x", "y"), require_all_targets=True)
    assert dialog._import_button.isEnabled() is False
    assert dialog._reason.text() == "This file has 1 column; x and y each need one."


def test_default_construction_keeps_the_at_least_one_gate():
    """Without ``require_all_targets`` (the series path), mapping only one of
    several targets is still a valid, partial import."""
    dialog = _dialog(
        text="time,voltage\n0,4.1\n", targets=("Time [s]", "Voltage [V]")
    )
    dialog._combos[1].setCurrentIndex(0)  # skip Voltage
    assert dialog._import_button.isEnabled() is True
    assert not dialog._reason.isVisible()


def test_default_construction_has_no_append_button():
    """``offer_append`` defaults False: the series path's dialog is
    byte-identical to before -- one "Import" button, no Replace/Append.

    Clicks the button rather than calling ``_choose()`` directly: PySide6's
    ``clicked`` signal carries a ``checked`` argument that a bare
    ``clicked.connect(self._choose)`` would pass straight through as ``mode``,
    turning ``accepted_mode`` into ``False`` instead of ``None`` -- calling
    ``_choose()`` by hand would never catch that regression.
    """
    dialog = _dialog()
    assert dialog._import_button.text() == "Import"
    assert len(dialog._confirm_buttons) == 1
    dialog._import_button.click()
    assert dialog.accepted_mode is None


def test_dialog_offer_append_records_the_chosen_mode():
    from ui_qt.cards.paste_dialog import PastePreviewResult

    dialog = _dialog(offer_append=True)
    assert dialog._import_button.text() == "Replace"
    assert len(dialog._confirm_buttons) == 2

    dialog._choose(PastePreviewResult.APPEND)

    assert dialog.accepted_mapping == (0, 1)
    assert dialog.accepted_mode == PastePreviewResult.APPEND


def test_dialog_offer_append_replace_button_also_records_its_mode():
    from ui_qt.cards.paste_dialog import PastePreviewResult

    dialog = _dialog(offer_append=True)
    dialog._import_button.click()

    assert dialog.accepted_mapping == (0, 1)
    assert dialog.accepted_mode == PastePreviewResult.REPLACE


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


def test_import_button_is_always_visible_not_only_when_expanded():
    """Import sits inline in the grid's +/-/Expand row now, the same surface
    an x/y table's import uses -- not gated on the expanded takeover."""
    card = _validation_card()
    assert not card._import_button.isHidden()
    card._grid._toggle_expanded()
    assert not card._import_button.isHidden()
    card._grid._toggle_expanded()
    assert not card._import_button.isHidden()


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
