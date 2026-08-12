"""Workspace page: activity-bar entry, default landing, info panel, the
board's start surface and drag-and-drop file opening.

Covers Step 7 (the Workspace page shell), Step 8 (the New-document models,
now rows on the start surface) and Step 9 (drag-and-drop) of the
top-bar/workspace redesign.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QLabel, QWidget

import ui_qt.main_window as main_window_module
import ui_qt.workspace_panel as workspace_panel_module
from core.document_factory import SUPPORTED_MODELS

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _mime_data_for(*paths) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def _drag_enter_event(*paths) -> QDragEnterEvent:
    mime = _mime_data_for(*paths)
    event = QDragEnterEvent(QPointF(0, 0).toPoint(), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    event._mime_keepalive = mime  # PySide6 does not keep the QMimeData arg alive on its own
    return event


def _drop_event(*paths) -> QDropEvent:
    mime = _mime_data_for(*paths)
    event = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    event._mime_keepalive = mime  # PySide6 does not keep the QMimeData arg alive on its own
    return event


def _fail_if_called(*args, **kwargs):
    raise AssertionError("This dialog should not have been shown")


def test_workspace_entry_exists_and_selecting_it_shows_workspace_page(app_driver):
    d = app_driver
    d.show_view("Editor")
    assert d.current_view_index() == 0

    d.show_view("Workspace")

    assert d.current_view_index() == 2
    assert d.activity_bar_selected_label() == "Workspace"


def test_app_launches_on_workspace_page_with_no_document(app_driver):
    assert app_driver.current_view_index() == 2
    assert app_driver.activity_bar_selected_label() == "Workspace"


def test_the_record_section_is_absent_with_no_document(app_driver):
    """The strip is one document's record, so with no document there is no
    section -- not a section saying it has nothing to say."""
    assert app_driver.workspace_info_text() == ""


def test_workspace_info_shows_identity_and_file_state_once_opened(
    app_driver, valid_spm_path
):
    app_driver.open(valid_spm_path)

    text = app_driver.workspace_info_text()
    assert "Title: Minimal valid SPM example" in text
    assert "Model: SPM · BPX 1.0.0" in text
    assert "Read as: JSON" in text
    assert "Checked: Complete · Valid" in text
    assert f"From: {valid_spm_path}" in text
    assert "Status: Saved" in text


def test_workspace_info_reflects_dirty_state(app_driver, spm_workfile):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()

    assert "Status: Unsaved changes" in app_driver.workspace_info_text()


def test_workspace_info_returns_to_saved_after_save(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    assert "Status: Unsaved changes" in d.workspace_info_text()

    d._w._save()

    assert "Status: Saved" in d.workspace_info_text()


def test_workspace_info_filename_updates_after_save_as(
    app_driver, spm_workfile, tmp_path, monkeypatch
):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    d._w._state.active.backing_file = None  # force the Save As path

    new_path = tmp_path / "renamed.json"
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(new_path), ""),
    )

    d._w._save()

    # Save re-captures the load record from the bytes it wrote, so the
    # From row names the file this document is now backed by.
    assert f"From: {new_path}" in d.workspace_info_text()
    assert "Status: Saved" in d.workspace_info_text()


def test_opening_from_workspace_page_switches_to_editor_page(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    assert d.current_view_index() == 2

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    d.click_workspace_open()

    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"
    assert d.identity_text() == "Minimal valid SPM example · BPX v1.0.0"
    assert d._w._state.active.document.identity.model == "SPM"


def test_opening_from_workspace_page_goes_through_discard_guard(
    app_driver, spm_workfile, valid_spm_path, monkeypatch
):
    """Open from the Workspace page reuses ``_confirm_discard_if_dirty``,
    the same guard exercised by the toolbar Open in the discard-guard tests.

    A document is already open, so ``_open()`` now shows the open-intent
    choice dialog first (M1) -- stubbed here to "Replace main" so the
    discard guard is exercised in isolation, same as before.
    """
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    assert d.status_text() == f"{spm_workfile.name} · Unsaved changes"
    original_status = d.status_text()

    monkeypatch.setattr(
        d._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.REPLACE_MAIN
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: main_window_module.QMessageBox.Cancel
    )
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    d.press_open_shortcut()

    assert d.status_text() == original_status


def test_main_card_shows_validity_and_contents(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)
    assert app_driver.workspace_validity_text() == "Valid"
    assert app_driver.workspace_main_name() == valid_spm_path.name
    # section/parameter counts come straight from the document, not invented.
    doc = app_driver._w._state.active.document
    assert (
        f"Contents: {doc.section_count} sections · {doc.parameter_count} parameters"
        in app_driver.workspace_info_text()
    )


def test_main_card_reports_errors_and_offers_the_route_to_them(
    app_driver, invalid_bpx_path
):
    app_driver.open(invalid_bpx_path)
    doc = app_driver._w._state.active.document
    assert not doc.is_valid
    assert app_driver.workspace_validity_text() == "1 error"
    # The page is not a dead end: the errors carry their own way to read them.
    assert app_driver.issue_route_text() == "Diagnostics ▸"


def test_document_card_badge_matches_partitioned_count_not_raw_diagnostics(
    warning_only_bpx_path, tmp_path, app_driver
):
    """The pill must report the same counts as the Diagnostics rail badge.

    ``warning_legacy_bpx_float.json`` with its Electrolyte conductivity
    corrupted to a string carries 4 raw diagnostics on that one field (one
    per failed union branch: float, int, function-expression, table) plus
    the fixture's pre-existing Header warning, but ``partition_issues``
    merges the field's float/int union pair into a single displayed error
    so the rest of the app shows 3 errors, 1 warning. The pill
    must match, not the raw ``document.error_count``/``warning_count`` (4/1).
    """
    import json

    raw = json.loads(warning_only_bpx_path.read_text("utf-8"))
    raw["Parameterisation"]["Electrolyte"]["Conductivity [S.m-1]"] = "not-a-number"
    workfile = tmp_path / "union_pair.json"
    workfile.write_text(json.dumps(raw), encoding="utf-8")

    app_driver.open_as_is(workfile)  # the base fixture is legacy BPX 0.1
    doc = app_driver._w._state.active.document
    assert (doc.error_count, doc.warning_count) == (4, 1), "premise: raw counts are 4/1"
    assert app_driver.workspace_validity_text() == "3 errors, 1 warning"


def test_an_empty_board_shows_the_start_surface_not_an_empty_card(app_driver):
    """Nothing open is not a dead end: the Main slot carries every way to
    fill it, and the main card is not on the board at all."""
    d = app_driver
    assert d.start_surface_visible()
    assert d.workspace_main_name() == ""
    assert d.workspace_info_text() == ""
    assert d.workspace_validity_text() == ""
    assert d.issue_route_text() == ""
    assert not d.workspace_record_visible()


def test_start_surface_offers_exactly_the_supported_models(app_driver):
    assert sorted(app_driver.workspace_new_model_options()) == sorted(SUPPORTED_MODELS)


def test_start_surface_offers_the_recent_files_that_still_exist(
    qtbot, tmp_path, valid_spm_path
):
    """A route that cannot be taken is not one, so a recent file that has
    gone is left out rather than shown struck through."""
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)
    gone = tmp_path / "gone.json"

    panel.set_workspaces(
        [],
        [],
        recent_files=[
            workspace_panel_module.RecentEntryView(
                path=str(valid_spm_path),
                name=valid_spm_path.name,
                exists=True,
                mtime=valid_spm_path.stat().st_mtime,
            ),
            workspace_panel_module.RecentEntryView(
                path=str(gone), name=gone.name, exists=False
            ),
        ],
    )

    surface = panel._start_surface
    assert surface.recent_row_labels() == [valid_spm_path.name]


def test_the_start_surface_opens_a_file_through_the_dialog(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    d.click_workspace_open()

    assert d._w._state.active.backing_file == valid_spm_path
    assert not d.start_surface_visible()


def test_start_surface_falls_back_to_the_model_name_with_no_descriptor(
    qtbot, monkeypatch
):
    """A model absent from ``_MODEL_DESCRIPTORS`` must still render (name
    only, blank descriptor), never crash -- the documented graceful-
    degradation fallback."""
    monkeypatch.setattr(workspace_panel_module, "SUPPORTED_MODELS", ("Mystery",))

    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    row = panel.findChild(QWidget, "NewButton_Mystery")
    assert row is not None
    assert row.findChild(QLabel, "StartRowName").text() == "Mystery"
    assert row.findChild(QLabel, "StartRowDetail").full_text() == ""


@pytest.mark.parametrize("model", SUPPORTED_MODELS)
def test_choosing_new_model_creates_document_and_switches_to_editor(app_driver, model):
    d = app_driver
    assert d.current_view_index() == 2

    d.click_workspace_new(model)

    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"
    assert d._w._state.active.document.identity.model == model
    # A scaffold was never loaded and never saved: no From row to state,
    # and the Status row says so in the record's own words.
    assert "Status: Unsaved changes · never saved" in d.workspace_info_text()
    assert "From:" not in d.workspace_info_text()


def test_a_new_document_is_never_offered_over_an_open_one(
    app_driver, spm_workfile, monkeypatch
):
    """New has no replace guard because it has nothing to replace: the
    surface that offers it is the empty Main slot, so an open document
    takes the whole route off the board rather than guarding it.

    A guard that fired here would be a dialog nobody could reach, so the
    test proves the absence of the route rather than the absence of the
    dialog.
    """
    d = app_driver
    d.open(spm_workfile)
    d.show_view("Workspace")

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", _fail_if_called
    )

    assert not d.start_surface_visible()
    assert d.workspace_new_model_options() == []


def test_choosing_a_model_on_a_filled_workspace_is_impossible_to_reach(app_driver):
    """The board never shows the start surface beside a document, so the
    two states cannot both be on screen."""
    d = app_driver
    assert d.start_surface_visible()
    d.click_workspace_new("DFN")
    assert not d.start_surface_visible()
    assert d.workspace_main_name() == "untitled.json"


# --- panel-level drag/drop filtering ------------------------------------
#
# These construct real QDragEnterEvent/QDropEvent instances and dispatch
# them straight to a bare WorkspacePanel, exercising the extension filter
# and single-file behaviour independent of MainWindow.


def test_drag_enter_accepts_a_supported_extension(qtbot, valid_spm_path):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    event = _drag_enter_event(valid_spm_path)
    panel.dragEnterEvent(event)

    assert event.isAccepted()


def test_drag_enter_ignores_an_unsupported_extension(qtbot, tmp_path):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    unsupported = tmp_path / "notes.txt"

    event = _drag_enter_event(unsupported)
    panel.dragEnterEvent(event)

    assert not event.isAccepted()


def test_drop_emits_file_dropped_for_the_first_supported_file_only(
    qtbot, valid_spm_path, tmp_path
):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")
    received: list[str] = []
    panel.file_dropped.connect(received.append)

    event = _drop_event(valid_spm_path, other)
    panel.dropEvent(event)

    assert received == [str(valid_spm_path)]
    assert event.isAccepted()


def test_drop_skips_a_leading_unsupported_file_to_reach_a_later_supported_one(
    qtbot, valid_spm_path, tmp_path
):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    unsupported = tmp_path / "notes.txt"
    received: list[str] = []
    panel.file_dropped.connect(received.append)

    event = _drop_event(unsupported, valid_spm_path)
    panel.dropEvent(event)

    assert received == [str(valid_spm_path)]
    assert event.isAccepted()


def test_drag_enter_accepts_an_uppercase_supported_extension(qtbot, tmp_path):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    uppercase = tmp_path / "SOMETHING.JSON"
    uppercase.write_text("{}", encoding="utf-8")

    event = _drag_enter_event(uppercase)
    panel.dragEnterEvent(event)

    assert event.isAccepted()


def test_drop_ignores_an_unsupported_extension_without_emitting(qtbot, tmp_path):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    unsupported = tmp_path / "notes.txt"
    received: list[str] = []
    panel.file_dropped.connect(received.append)

    event = _drop_event(unsupported)
    panel.dropEvent(event)

    assert received == []
    assert not event.isAccepted()


# --- MainWindow wiring: drop goes through the same guard/open/error path
# as the toolbar/Workspace Open button ------------------------------------


def test_dropping_a_valid_file_opens_it_and_switches_to_editor(app_driver, valid_spm_path):
    d = app_driver
    assert d.current_view_index() == 2

    d.drop_file_on_workspace(valid_spm_path)

    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"
    assert d.identity_text() == "Minimal valid SPM example · BPX v1.0.0"
    assert d._w._state.active.document.identity.model == "SPM"


def test_dropping_a_file_goes_through_discard_guard_and_cancel_aborts(
    app_driver, spm_workfile, valid_spm_path, monkeypatch
):
    """A document is already open, so the drop now shows the open-intent
    choice dialog first (M1) -- stubbed here to "Replace main" so the
    discard guard is exercised in isolation, same as before."""
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    original_identity = d.identity_text()
    original_status = d.status_text()
    assert "Unsaved changes" in original_status

    d.show_view("Workspace")  # starting off the Editor page so a wrongful
    # switch-to-Editor on the abort path would actually move the index

    monkeypatch.setattr(
        d._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.REPLACE_MAIN
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: main_window_module.QMessageBox.Cancel
    )

    d.drop_file_on_workspace(valid_spm_path)

    assert d.current_view_index() == 2
    assert d.activity_bar_selected_label() == "Workspace"
    assert d.identity_text() == original_identity
    assert d.status_text() == original_status  # dirty state retained, nothing opened


def test_dropping_a_file_discard_guard_proceeds_on_discard(
    app_driver, spm_workfile, valid_spm_path, monkeypatch
):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()

    monkeypatch.setattr(
        d._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.REPLACE_MAIN
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: main_window_module.QMessageBox.Discard
    )

    d.drop_file_on_workspace(valid_spm_path)

    assert d.identity_text() == "Minimal valid SPM example · BPX v1.0.0"
    assert d._w._state.active.document.identity.model == "SPM"
    assert d.current_view_index() == 0


def test_dropping_an_unsupported_extension_is_a_no_op(app_driver, tmp_path):
    d = app_driver
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("hello", encoding="utf-8")

    d.drop_file_on_workspace(unsupported)

    assert d.current_view_index() == 2
    assert d.workspace_info_text() == ""


def test_dropping_an_unparseable_file_shows_the_load_error_dialog(
    app_driver, tmp_path, monkeypatch
):
    d = app_driver
    broken = tmp_path / "broken.json"
    broken.write_text("{not valid json", encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical", lambda *a, **k: calls.append(a)
    )

    d.drop_file_on_workspace(broken)

    assert len(calls) == 1
    assert d.current_view_index() == 2  # stayed on Workspace, nothing opened
    assert d.workspace_info_text() == ""


def test_document_card_names_what_is_still_outstanding(app_driver):
    """A fresh DFN's badge names the incomplete count -- and does not say
    "Valid": bpx aborts its staged run over the missing required fields, so
    no verdict exists to state (H2). "Not checked" is the same word the
    Inspector uses for a parameter in that state."""
    app_driver._w._new("DFN")
    assert app_driver._w._state.active.document.validation_completed is False

    text = app_driver.workspace_validity_text()
    assert text.startswith("Not checked · ")
    assert text.endswith(" incomplete")


def test_an_aborted_run_badges_not_checked_never_valid(
    app_driver, tmp_path, valid_spm_dict
):
    """One deleted required field aborts bpx's staged run (State is never
    judged) and the lone "Field required" error is absorbed into the
    incomplete count -- zero errors on show. Zero errors from an aborted run
    is not a verdict, so the badge must not read "Valid" (H2)."""
    import copy
    import json

    raw = copy.deepcopy(valid_spm_dict)
    del raw["Parameterisation"]["Cell"]["Electrode area [m2]"]
    path = tmp_path / "aborted.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    d = app_driver.open(path)

    assert d._w._state.active.document.validation_completed is False
    assert d.workspace_validity_text() == "Not checked · 1 incomplete"


def test_a_complete_document_says_only_valid(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)

    assert "incomplete" not in app_driver.workspace_validity_text()


# --- the Phase 4 record: editable identity rows + the fact plaque ----------


def test_record_title_edit_commits_through_setvalue(app_driver, spm_workfile, qtbot):
    """Typing in the record's Title row lands in Header.Title through the
    same command path as the Header card (D6), so it marks the session
    dirty and every surface refreshes."""
    d = app_driver
    d.open(spm_workfile)
    ws = d._w._workspace

    ws._info_title.begin_edit()
    ws._info_title._editor.setText("Renamed cell")
    qtbot.keyClick(ws._info_title._editor, Qt.Key_Return)

    session = d._w._state.active
    assert session.document.raw["Header"]["Title"] == "Renamed cell"
    assert session.dirty
    assert "Title: Renamed cell" in d.workspace_info_text()

    session.undo()
    d._w._refresh_all()
    assert "Title: Minimal valid SPM example" in d.workspace_info_text()


def test_record_citation_edit_reaches_header_references(app_driver, spm_workfile, qtbot):
    """The Citation row edits the Header's ``References`` field (D1: the
    spec field surfaces as Citation, the code path keeps the spec name)."""
    d = app_driver
    d.open(spm_workfile)
    ws = d._w._workspace

    ws._info_citation.begin_edit()
    ws._info_citation._editor.setText("Chen et al 2020")
    qtbot.keyClick(ws._info_citation._editor, Qt.Key_Return)

    assert d._w._state.active.document.raw["Header"]["References"] == "Chen et al 2020"
    assert "Citation: Chen et al 2020" in d.workspace_info_text()


def test_record_bare_enter_never_commits(app_driver, spm_workfile, qtbot):
    """An untouched editor commits nothing: no command, no dirty -- the
    card discipline, translated to the record."""
    d = app_driver
    d.open(spm_workfile)
    ws = d._w._workspace

    ws._info_title.begin_edit()
    qtbot.keyClick(ws._info_title._editor, Qt.Key_Return)

    assert not d._w._state.active.dirty


def test_record_escape_reverts_the_draft(app_driver, spm_workfile, qtbot):
    d = app_driver
    d.open(spm_workfile)
    ws = d._w._workspace

    ws._info_title.begin_edit()
    ws._info_title._editor.setText("abandoned")
    qtbot.keyClick(ws._info_title._editor, Qt.Key_Escape)

    assert not d._w._state.active.dirty
    assert "Title: Minimal valid SPM example" in d.workspace_info_text()


def test_record_empty_identity_rows_state_their_absence(app_driver, valid_spm_dict, tmp_path):
    """An absent Description/Citation shows its ghost invitation rather
    than nothing -- absence stated (the argument that rejected concept C)."""
    import json

    valid_spm_dict["Header"].pop("Description", None)
    valid_spm_dict["Header"].pop("References", None)
    work = tmp_path / "bare.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    d = app_driver
    d.open(work)
    ws = d._w._workspace
    assert ws._info_description._display.text() == "Add a description…"
    assert ws._info_citation._display.text() == "Add a citation…"


def test_record_states_yaml_comments_fact(app_driver, valid_spm_dict, tmp_path, qtbot):
    """A YAML file with comments carries the fact on its Read as row, and
    the row expands to the consequence sentence (D4)."""
    import yaml as yaml_module

    work = tmp_path / "commented.yaml"
    work.write_text(
        "# calibration notes\n" + yaml_module.safe_dump(valid_spm_dict),
        encoding="utf-8",
    )

    d = app_driver
    d.open(work)
    ws = d._w._workspace
    text = d.workspace_info_text()
    assert "Read as: YAML" in text
    assert "has comments" in text

    fact = ws._fact_read_as
    assert not fact.is_expanded()
    qtbot.mouseClick(fact, Qt.LeftButton)
    assert fact.is_expanded()
    assert "comments and formatting will not survive" in fact.detail_text()


def test_record_states_legacy_conversion_fact(app_driver, fixtures_dir):
    """A v0.x file's Checked row names the conversion bpx judged, and its
    detail names the file and what the conversion did (finding 1)."""
    from core.bpx_gateway import BPX_VERSION

    d = app_driver
    d.open_as_is(fixtures_dir / "nmc_pouch_cell_BPX.json")
    ws = d._w._workspace

    assert f"Checked: As a BPX {BPX_VERSION} conversion" in d.workspace_info_text()
    detail = ws._fact_checked.detail_text()
    assert "nmc_pouch_cell_BPX.json is BPX 0.1" in detail
    assert "converted copy" in detail


def test_record_refresh_mid_edit_keeps_the_draft(app_driver, spm_workfile, qtbot):
    """A refresh arriving while the user is typing must not clobber the
    editor -- only the seed moves."""
    d = app_driver
    d.open(spm_workfile)
    ws = d._w._workspace

    ws._info_title.begin_edit()
    ws._info_title._editor.setText("half-typed draft")
    d._w._refresh_all()

    assert ws._info_title._editor.isVisible() or not ws._info_title._editor.isHidden()
    assert ws._info_title._editor.text() == "half-typed draft"


def test_the_workspace_page_sections_share_one_wider_measure(app_driver):
    """The page is cards and keyed rows, not prose: capped at the reading
    measure the four reference slots got ~90 px each and elided their names
    away. Both sections take the same cap, so the page has one right edge."""
    from ui_qt import style
    from ui_qt.group_box import TintedSection

    page_measure = workspace_panel_module._PAGE_MEASURE
    assert page_measure > style.CONTENT_MEASURE

    workspace = app_driver._w._workspace
    for object_name in ("WorkspaceBoardSection", "WorkspaceMainSection"):
        section = workspace.findChild(QWidget, object_name)
        assert section is not None, object_name
        assert section.body.maximumWidth() == page_measure, object_name
        assert section.header.maximumWidth() == page_measure, object_name

    # A section that asks for nothing still gets the reading measure.
    plain = TintedSection("Plain", object_name="WorkspaceMainSection")
    assert plain.body.maximumWidth() == style.CONTENT_MEASURE
