"""Headless smoke test: the Qt frontend boots and drives a full edit cycle."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui_qt.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_window_boots_and_edits(valid_spm_bytes):
    _app()
    window = MainWindow()
    window._state.load(valid_spm_bytes, "spm_example_valid.json")
    window._refresh_all()
    assert window._state.document.is_valid

    path = ("Header", "Model")
    window._jump_to_path(path)
    window._state.apply_value(path, "DFN")
    window._on_committed()
    assert window._state.document.raw["Header"]["Model"] == "DFN"
