"""Fixed top bar (identity + actions) and bottom status bar split.

Covers Steps 2+3 of the top-bar/workspace redesign: the top bar's identity
label composed from ``document.identity``, Save/Export enabled state, and the
bottom status bar showing only file name + Saved/Unsaved changes (never the Title).

The identity label carries only Title and BPX version -- Model is omitted
and is edited in the Editor instead, via the normal ``Header.Model`` enum
card.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module


def test_no_document_shows_placeholder_and_disables_actions(app_driver):
    assert app_driver.identity_text() == "No document"
    assert app_driver.save_enabled() is False
    assert app_driver.export_enabled() is False
    assert app_driver.status_text() == ""


def test_identity_shows_title_and_version(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)

    assert app_driver.identity_text() == "Minimal valid SPM example · BPX v1.0.0"
    assert app_driver.save_enabled() is True
    assert app_driver.export_enabled() is True


def test_identity_falls_back_to_filename_when_title_empty(app_driver, valid_spm_dict, tmp_path):
    valid_spm_dict["Header"]["Title"] = ""
    work = tmp_path / "no_title_example.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.identity_text() == "no_title_example.json · BPX v1.0.0"


def test_identity_unaffected_by_missing_model(app_driver, valid_spm_dict, tmp_path):
    """The identity label carries no Model segment, so clearing
    ``Header.Model`` changes nothing about it."""
    valid_spm_dict["Header"]["Model"] = ""
    work = tmp_path / "no_model_example.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.identity_text() == "Minimal valid SPM example · BPX v1.0.0"


def test_identity_label_omits_model(app_driver, valid_spm_path):
    """Even with a declared Model, the identity label must not carry it --
    Model is edited in the Editor instead."""
    app_driver.open(valid_spm_path)

    assert app_driver.identity_text() == "Minimal valid SPM example · BPX v1.0.0"


def test_identity_title_only_has_no_dangling_version_or_separator(app_driver, valid_spm_dict, tmp_path):
    valid_spm_dict["Header"]["BPX"] = ""
    work = tmp_path / "title_only_example.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.identity_text() == "Minimal valid SPM example"


def test_identity_falls_back_to_filename_when_all_header_fields_empty(app_driver, valid_spm_dict, tmp_path):
    valid_spm_dict["Header"]["Title"] = ""
    valid_spm_dict["Header"]["Model"] = ""
    valid_spm_dict["Header"]["BPX"] = ""
    work = tmp_path / "empty_header_example.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.identity_text() == "empty_header_example.json"


def test_status_bar_shows_filename_and_state_not_title(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)

    assert app_driver.status_text() == f"{valid_spm_path.name} · Saved"
    assert "Minimal valid SPM example" not in app_driver.status_text()


def test_status_bar_reflects_dirty_state(app_driver, spm_workfile):
    capacity = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    app_driver.open(spm_workfile).go_to(capacity).edit_field(6.0).commit()

    assert app_driver.status_text() == f"{spm_workfile.name} · Unsaved changes"


# ---------------------------------------------------------------------------
# Keyboard shortcuts
#
# Save and Open are the two most-repeated document actions and had no key at
# all. They are bound differently on purpose: Save's sequence rides on the
# toolbar QAction, so it inherits that action's enabled state and goes dead
# exactly where the button greys out; Open has no toolbar button (it lives on
# the Workspace page) and so needs a standalone window-level QShortcut, which
# stays live from every page. Ctrl+N is deliberately unbound: New takes a
# model, so there is no single action for a key to mean.
# ---------------------------------------------------------------------------

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def test_save_action_carries_the_platform_save_shortcut(app_driver):
    from PySide6.QtGui import QKeySequence

    assert app_driver.save_shortcut() == QKeySequence(QKeySequence.Save).toString()


def test_save_shortcut_is_window_wide(app_driver):
    """Save is never focus-aware, unlike Undo: whatever widget holds focus,
    the key means the document command."""
    from PySide6.QtCore import Qt

    assert app_driver._w._save_action.shortcutContext() == Qt.WindowShortcut


def test_no_standalone_shortcut_claims_the_save_key(app_driver):
    """Ctrl+S must reach _save only through the action, because that is what
    makes it inherit the enabled gate below. A second QShortcut carrying the
    same key would both bypass that gate and go ambiguous against the action.
    """
    from PySide6.QtGui import QKeySequence, QShortcut

    save_key = QKeySequence(QKeySequence.Save).toString()
    claimed = [sc.key().toString() for sc in app_driver._w.findChildren(QShortcut) if sc.key().toString() == save_key]

    assert claimed == []


def test_save_key_is_gated_by_the_action_it_rides_on(app_driver, spm_workfile):
    """A disabled QAction's shortcut is never dispatched, so binding the key
    to the action is what leaves it dead exactly where the button greys."""
    assert app_driver.save_enabled() is False

    app_driver.open(spm_workfile)

    assert app_driver.save_enabled() is True


def test_open_shortcut_is_the_platform_open_key(app_driver):
    from PySide6.QtGui import QKeySequence

    assert app_driver.open_shortcut() == QKeySequence(QKeySequence.Open).toString()


def test_open_shortcut_opens_a_file_with_none_loaded(app_driver, valid_spm_path, monkeypatch):
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    app_driver.press_open_shortcut()

    assert app_driver.status_text() == f"{valid_spm_path.name} · Saved"


def test_open_shortcut_reaches_open_from_the_editor_page(app_driver, valid_spm_path, spm_workfile, monkeypatch):
    """The gap the shortcut exists to close: Open's only button is on the
    Workspace page, so from the Editor there was no route to it at all."""
    app_driver.open(spm_workfile).show_view("Editor")
    assert app_driver.current_view_name() == "Editor"

    monkeypatch.setattr(
        app_driver._w,
        "_ask_open_intent",
        lambda filename: main_window_module.OpenIntent.REPLACE_MAIN,
    )
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    app_driver.press_open_shortcut()

    assert app_driver.status_text() == f"{valid_spm_path.name} · Saved"


def test_open_shortcut_reaches_open_from_the_diagnostics_page(app_driver, valid_spm_path, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).show_view("Diagnostics")
    assert app_driver.current_view_name() == "Diagnostics"

    monkeypatch.setattr(
        app_driver._w,
        "_ask_open_intent",
        lambda filename: main_window_module.OpenIntent.REPLACE_MAIN,
    )
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    app_driver.press_open_shortcut()

    assert app_driver.status_text() == f"{valid_spm_path.name} · Saved"
