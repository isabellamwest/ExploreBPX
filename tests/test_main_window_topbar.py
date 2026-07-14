"""Fixed top bar (identity + actions) and bottom status bar split.

Covers Steps 2+3 of the top-bar/workspace redesign: the top bar's identity
label composed from ``document.identity``, Save/Export enabled state, and the
bottom status bar showing only file name + Saved/Modified (never the Title).

Since the completion track's Phase 4, the Model segment lives in the
top-bar Model chip rather than the identity label (see
``test_main_window_model_chip.py``) -- the identity label carries only
Title and BPX version.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")


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


def test_identity_falls_back_to_filename_when_title_empty(
    app_driver, valid_spm_dict, tmp_path
):
    valid_spm_dict["Header"]["Title"] = ""
    work = tmp_path / "no_title_example.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.identity_text() == "no_title_example.json · BPX v1.0.0"


def test_identity_unaffected_by_missing_model(
    app_driver, valid_spm_dict, tmp_path
):
    """The identity label no longer carries Model at all (Phase 4's chip
    does), so clearing ``Header.Model`` changes nothing about it."""
    valid_spm_dict["Header"]["Model"] = ""
    work = tmp_path / "no_model_example.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.identity_text() == "Minimal valid SPM example · BPX v1.0.0"


def test_identity_title_only_has_no_dangling_version_or_separator(
    app_driver, valid_spm_dict, tmp_path
):
    valid_spm_dict["Header"]["BPX"] = ""
    work = tmp_path / "title_only_example.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.identity_text() == "Minimal valid SPM example"


def test_identity_falls_back_to_filename_when_all_header_fields_empty(
    app_driver, valid_spm_dict, tmp_path
):
    valid_spm_dict["Header"]["Title"] = ""
    valid_spm_dict["Header"]["Model"] = ""
    valid_spm_dict["Header"]["BPX"] = ""
    work = tmp_path / "empty_header_example.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.identity_text() == "empty_header_example.json"


def test_status_bar_shows_filename_and_state_not_title(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)

    assert app_driver.status_text() == f"{valid_spm_path.name}  |  Saved"
    assert "Minimal valid SPM example" not in app_driver.status_text()


def test_status_bar_reflects_dirty_state(app_driver, spm_workfile):
    capacity = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    app_driver.open(spm_workfile).go_to(capacity).edit_field(6.0).commit()

    assert app_driver.status_text() == f"{spm_workfile.name}  |  Modified"
