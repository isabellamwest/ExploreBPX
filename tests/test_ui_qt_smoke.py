"""Headless smoke test: the Qt frontend boots and drives a full edit cycle."""

from __future__ import annotations

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui_qt.main_window import MainWindow


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
