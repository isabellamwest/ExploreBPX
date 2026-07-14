"""Top-bar Model chip: the completion track's Phase 4 set-model action.

The Model segment moved out of the identity label (see
``test_main_window_topbar.py``) into a small menu button beside it, per
PLAN-completion-track.md decision J. Selecting the currently-declared model
is a deliberate no-op -- no command runs, so neither the undo stack nor the
dirty flag changes. Selecting another model routes through the existing
``apply_value(("Header", "Model"), ...)`` -> ``ChangeModel`` spine, which also
scaffolds the target model's required-but-missing sections in the same undo
step -- no new command, no new UI concept beyond the chip itself.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from core.document_factory import SUPPORTED_MODELS


# ------------------------------------------------------------------
# Label + enablement
# ------------------------------------------------------------------


def test_chip_shows_declared_model(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)

    assert app_driver.model_chip_text() == "SPM"
    assert app_driver.model_chip_enabled() is True


def test_chip_shows_no_model_when_model_absent_from_raw(
    app_driver, valid_spm_dict, tmp_path
):
    del valid_spm_dict["Header"]["Model"]
    work = tmp_path / "no_model.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.model_chip_text() == "No model"
    assert app_driver.model_chip_enabled() is True  # Header still exists


def test_chip_disabled_with_no_document(app_driver):
    assert app_driver.model_chip_enabled() is False


def test_chip_disabled_when_header_absent(app_driver, valid_spm_dict, tmp_path):
    del valid_spm_dict["Header"]
    work = tmp_path / "no_header.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.model_chip_enabled() is False


def test_identity_label_no_longer_carries_the_model(app_driver, valid_spm_path):
    """The chip is the single home for Model; the identity label must not
    duplicate it (plan's test 6)."""
    app_driver.open(valid_spm_path)

    assert app_driver.identity_text() == "Minimal valid SPM example · BPX v1.0.0"
    assert app_driver.model_chip_text() == "SPM"


# ------------------------------------------------------------------
# Menu contents
# ------------------------------------------------------------------


def test_menu_lists_supported_models_with_current_checked(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)

    assert app_driver.model_chip_options() == list(SUPPORTED_MODELS)
    assert app_driver.model_chip_checked() == ["SPM"]


def test_garbage_current_model_checks_nothing_but_menu_still_works(
    app_driver, valid_spm_dict, tmp_path
):
    valid_spm_dict["Header"]["Model"] = "Mystery"
    work = tmp_path / "garbage_model.json"
    work.write_text(json.dumps(valid_spm_dict), encoding="utf-8")

    app_driver.open(work)

    assert app_driver.model_chip_text() == "Mystery"
    assert app_driver.model_chip_checked() == []

    app_driver.select_model("SPMe")

    assert app_driver.model_chip_text() == "SPMe"
    assert app_driver.model_chip_checked() == ["SPMe"]
    assert app_driver._w._state.active.document.raw["Header"]["Model"] == "SPMe"


# ------------------------------------------------------------------
# Selecting the current model: no-op
# ------------------------------------------------------------------


def test_selecting_current_model_is_a_no_op(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)
    session = app_driver._w._state.active
    assert session.can_undo is False
    assert session.dirty is False

    app_driver.select_model("SPM")

    assert session.can_undo is False
    assert session.dirty is False
    assert app_driver.model_chip_text() == "SPM"


# ------------------------------------------------------------------
# Selecting a different model: end to end
# ------------------------------------------------------------------


def test_selecting_different_model_scaffolds_sections_in_one_undo_step(
    app_driver, valid_spm_path
):
    app_driver.open(valid_spm_path)
    session = app_driver._w._state.active
    assert "Electrolyte" not in session.document.raw["Parameterisation"]
    assert "Separator" not in session.document.raw["Parameterisation"]

    app_driver.select_model("SPMe")

    raw = session.document.raw
    assert raw["Header"]["Model"] == "SPMe"
    assert "Electrolyte" in raw["Parameterisation"]
    assert "Separator" in raw["Parameterisation"]
    assert app_driver.model_chip_text() == "SPMe"
    assert app_driver.model_chip_checked() == ["SPMe"]
    assert app_driver.identity_text() == "Minimal valid SPM example · BPX v1.0.0"
    assert session.can_undo is True

    app_driver.undo()

    raw_after_undo = session.document.raw
    assert raw_after_undo["Header"]["Model"] == "SPM"
    assert "Electrolyte" not in raw_after_undo["Parameterisation"]
    assert "Separator" not in raw_after_undo["Parameterisation"]
    assert app_driver.model_chip_text() == "SPM"
    assert session.can_undo is False
    assert session.can_redo is True

    app_driver.redo()

    raw_after_redo = session.document.raw
    assert raw_after_redo["Header"]["Model"] == "SPMe"
    assert "Electrolyte" in raw_after_redo["Parameterisation"]
    assert "Separator" in raw_after_redo["Parameterisation"]
    assert app_driver.model_chip_text() == "SPMe"


# ------------------------------------------------------------------
# open_model_chooser(): the public seam for Phase 5's declare-model row
# ------------------------------------------------------------------


def test_open_model_chooser_noops_when_disabled(app_driver, monkeypatch):
    called = []
    monkeypatch.setattr(app_driver._w._model_chip, "showMenu", lambda: called.append(True))
    assert app_driver.model_chip_enabled() is False

    app_driver.open_model_chooser()

    assert called == []


def test_open_model_chooser_shows_menu_when_enabled(app_driver, valid_spm_path, monkeypatch):
    app_driver.open(valid_spm_path)
    called = []
    monkeypatch.setattr(app_driver._w._model_chip, "showMenu", lambda: called.append(True))
    assert app_driver.model_chip_enabled() is True

    app_driver.open_model_chooser()

    assert called == [True]
