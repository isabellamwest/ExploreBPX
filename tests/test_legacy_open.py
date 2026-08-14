"""The legacy open prompt and the read-only main document.

A detectably legacy BPX v0.x file opened as the main document routes
through one prompt -- converted copy, as-is read-only, or cancel -- from
every route (Open dialog, drag-and-drop, New-from-file, the stale dialog's
Reload; they all funnel through ``open_document``/``_route_legacy``). The
as-is path installs a session whose ``read_only`` flag the state layer
enforces (``ReadOnlyDocumentError``) and the UI mirrors by disabling every
editing affordance. The prompt is the overridable ``_ask_legacy_intent``
seam (the ``_ask_open_intent`` convention); one test exercises the real
QMessageBox via the zero-delay idiom.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from platform_facts import assert_alert_title
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.bpx_gateway import BPX_VERSION
from core.commands import SetValue
from state.app_state import AppState
from state.document_session import ReadOnlyDocumentError
from ui_qt.main_window import LegacyIntent

_LEGACY = "warning_legacy_bpx_float.json"
_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _arm_legacy(window, monkeypatch, intent, calls=None):
    def fake_ask(filename, version):
        if calls is not None:
            calls.append((filename, version))
        return intent

    monkeypatch.setattr(window, "_ask_legacy_intent", fake_ask)


# ----------------------------------------------------------------------
# state layer
# ----------------------------------------------------------------------


def test_legacy_version_probe(fixtures_dir, valid_spm_path):
    state = AppState()
    assert state.legacy_version(fixtures_dir / _LEGACY) == "0.1"
    assert state.legacy_version(valid_spm_path) is None


def test_open_read_only_installs_a_sealed_session(fixtures_dir):
    state = AppState()
    state.open_read_only(fixtures_dir / _LEGACY)
    session = state.active
    assert session.read_only is True
    assert session.backing_file is None
    assert session.dirty is False
    assert session.load_record.is_legacy is True
    assert session.load_record.source.endswith(_LEGACY)
    with pytest.raises(ReadOnlyDocumentError):
        session.execute_command(SetValue(("Header", "Title"), "x"))
    with pytest.raises(ReadOnlyDocumentError):
        session.apply_value(("Header", "Title"), "x")
    with pytest.raises(ReadOnlyDocumentError):
        session.save()


def test_open_converted_copy_installs_a_v1_unsaved_document(fixtures_dir):
    state = AppState()
    state.open_converted_copy(fixtures_dir / _LEGACY)
    session = state.active
    assert session.read_only is False
    assert session.dirty is True
    assert session.backing_file is None
    assert session.document.filename == "warning_legacy_bpx_float (converted).json"
    # bpx's own converter ran: the content is no longer detectably legacy,
    # and the record keeps the source's provenance.
    assert session.load_record.is_legacy is False
    assert session.load_record.source.endswith(_LEGACY)
    assert session.document.raw["Header"]["BPX"] != "0.1"


# ----------------------------------------------------------------------
# routing
# ----------------------------------------------------------------------


def test_non_legacy_open_never_asks(app_driver, spm_workfile, monkeypatch):
    calls = []
    _arm_legacy(app_driver._w, monkeypatch, LegacyIntent.CANCEL, calls)
    app_driver.open(spm_workfile)
    assert calls == []
    assert app_driver._w._state.active is not None


def test_legacy_cancel_leaves_everything_unchanged(app_driver, spm_workfile, fixtures_dir, monkeypatch):
    d = app_driver
    d.open(spm_workfile)
    before = d._w._state.active
    _arm_legacy(d._w, monkeypatch, LegacyIntent.CANCEL)
    d._w.open_document(fixtures_dir / _LEGACY)
    assert d._w._state.active is before


def test_legacy_converted_copy_route(app_driver, fixtures_dir, monkeypatch):
    d = app_driver
    calls = []
    _arm_legacy(d._w, monkeypatch, LegacyIntent.CONVERTED_COPY, calls)
    d._w.open_document(fixtures_dir / _LEGACY)
    assert calls == [(_LEGACY, "0.1")]
    session = d._w._state.active
    assert session.read_only is False
    assert session.dirty is True
    assert "(converted)" in session.document.filename
    # An ordinary unsaved document: Save stays live (routing to Save As).
    assert d._w._save_action.isEnabled()


# ----------------------------------------------------------------------
# the read-only main document
# ----------------------------------------------------------------------


def test_as_is_read_only_disables_every_editing_affordance(app_driver, fixtures_dir):
    d = app_driver
    d.open_as_is(fixtures_dir / _LEGACY)
    w = d._w
    assert w._state.active.read_only is True
    assert w._save_action.isEnabled() is False
    assert w._export_action.isEnabled() is True
    assert w._status_label.text().endswith("Read-only")
    assert w._compose_identity_text().endswith("Read-only")

    ws = w._workspace
    assert ws._fact_status.text() == "Read-only"
    assert not ws._main_card._read_only_tag.isHidden()
    assert ws._info_title._editable is False
    assert ws._info_description._editable is False
    assert ws._info_citation._editable is False

    assert w._params._add_button.isHidden()
    root = w._state.active.document.tree
    assert w._tree._build_menu(root).isEmpty()


def test_as_is_read_only_card_is_the_read_only_view(app_driver, fixtures_dir):
    d = app_driver
    d.open_as_is(fixtures_dir / _LEGACY)
    d.go_to(_CAPACITY)
    card = d._w._inspector._card
    assert card is not None
    assert card.is_editable is False


def test_save_refuses_on_a_read_only_session(app_driver, fixtures_dir):
    d = app_driver
    d.open_as_is(fixtures_dir / _LEGACY)
    assert d._w._save() is False


# ----------------------------------------------------------------------
# one real-dialog test (the rest monkeypatch the box)
# ----------------------------------------------------------------------


def test_legacy_prompt_real_box_words_and_default(app_driver):
    window = app_driver._w
    captured: dict = {}

    def _cancel():
        box = QApplication.instance().activeModalWidget()
        if box is not None:
            captured["title"] = box.windowTitle()
            captured["text"] = box.text()
            captured["informative"] = box.informativeText()
            captured["labels"] = [b.text() for b in box.buttons()]
            captured["default"] = box.defaultButton().text()
            for button in box.buttons():
                if button.text() == "Cancel":
                    button.click()
                    return

    QTimer.singleShot(0, _cancel)
    intent = window._ask_legacy_intent("lgm50_v0.json", "0.4")

    assert intent is LegacyIntent.CANCEL
    assert_alert_title(captured["title"], "Open lgm50_v0.json")
    assert captured["text"] == (f"lgm50_v0.json is BPX 0.4. Editing and checking here use BPX {BPX_VERSION}.")
    assert captured["informative"] == (
        f"Open converted copy starts a new unsaved document in BPX {BPX_VERSION}. "
        "The conversion is approximate: State synthesised, initial SOC set to 1, "
        "lumped thermal conductivity dropped. lgm50_v0.json is not changed.\n\n"
        "Open as-is shows the file exactly as it is on disk, read-only. "
        "bpx checks a converted copy."
    )
    assert set(captured["labels"]) == {
        "Open converted copy",
        "Open as-is, read-only",
        "Cancel",
    }
    assert captured["default"] == "Open converted copy"
