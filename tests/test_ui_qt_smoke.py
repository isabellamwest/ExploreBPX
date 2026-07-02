"""Headless smoke test: the Qt frontend boots and drives a full edit cycle."""

from __future__ import annotations

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui_qt.main_window import MainWindow
from ui_qt.inspector import InspectorPanel
from state.app_state import AppState


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_window_boots_and_edits(valid_spm_path, tmp_path):
    # Use a writable copy so the test session's backing_file never points
    # at the repository example file. Avoids accidental writes on save.
    work = tmp_path / "spm_test.json"
    shutil.copy(valid_spm_path, work)

    _app()
    window = MainWindow()
    window._state.open(work)
    window._refresh_all()
    assert window._state.active.document.is_valid

    path = ("Header", "Model")
    window._jump_to_path(path)
    window._state.active.apply_value(path, "DFN")
    window._on_committed()
    assert window._state.active.document.raw["Header"]["Model"] == "DFN"


def test_inspector_reset_clears_invalid_draft_badge(valid_spm_path):
    _app()
    state = AppState()
    state.open(valid_spm_path)
    assert state.active.document.is_valid

    path = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    parameter = state.active.document.find_parameter(path)
    assert parameter is not None
    original = parameter.value

    inspector = InspectorPanel(state)
    inspector.show_parameter(parameter)
    assert inspector._badge.text() == "Valid"

    inspector._card._edit.setText("not-a-number")
    inspector._validate_draft()
    assert inspector._badge.text() == "Invalid"

    inspector._card._on_inline_reset()
    assert inspector._card.value() == original
    assert inspector._badge.text() == "Valid"


def test_inspector_reset_restores_committed_invalid_badge(valid_spm_path):
    _app()
    state = AppState()
    state.open(valid_spm_path)

    path = ("Header", "Model")
    state.active.apply_value(path, "not-a-model")
    assert not state.active.document.is_valid

    parameter = state.active.document.find_parameter(path)
    assert parameter is not None
    assert parameter.has_errors

    inspector = InspectorPanel(state)
    inspector.show_parameter(parameter)
    assert inspector._badge.text() == "Invalid"

    inspector._card._select("SPM")
    inspector._validate_draft()
    assert inspector._badge.text() == "Valid"

    inspector._card._on_inline_reset()
    assert inspector._card.value() == "not-a-model"
    assert inspector._badge.text() == "Invalid"
