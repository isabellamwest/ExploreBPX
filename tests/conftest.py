"""Shared pytest fixtures and import path setup.

Adds the ``app`` directory to ``sys.path`` so the project packages import the
same way they do when the application is launched from the repository root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Qt tests run headless. Set this before any PySide6 import happens.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
EXAMPLES_DIR = REPO_ROOT / "examples"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES_DIR


@pytest.fixture
def valid_spm_path() -> Path:
    return EXAMPLES_DIR / "spm_example_valid.json"


@pytest.fixture
def valid_spm_bytes() -> bytes:
    return (EXAMPLES_DIR / "spm_example_valid.json").read_bytes()


@pytest.fixture
def valid_spm_dict() -> dict:
    import json

    return json.loads((EXAMPLES_DIR / "spm_example_valid.json").read_text("utf-8"))


@pytest.fixture
def invalid_bpx_path() -> Path:
    """An example file that opens successfully but fails BPX validation."""
    return EXAMPLES_DIR / "invalid_blended_state_mismatch.json"


@pytest.fixture
def warning_only_bpx_path() -> Path:
    """An example file that is valid but emits a warning-severity issue."""
    return EXAMPLES_DIR / "warning_legacy_bpx_float.json"


@pytest.fixture
def spm_workfile(valid_spm_path, tmp_path) -> Path:
    """A writable copy of the valid SPM example.

    Using a copy keeps a session's ``backing_file`` off the repository example
    so tests can exercise the save path without risking the fixture file.
    """
    import shutil

    work = tmp_path / "spm_workfile.json"
    shutil.copy(valid_spm_path, work)
    return work


@pytest.fixture
def main_window(qtbot):
    """A live :class:`MainWindow` with no document open.

    Skips cleanly when PySide6 is unavailable so the behavioural suite still
    runs in headless-only environments.
    """
    pytest.importorskip("PySide6")
    from ui_qt.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    return window


@pytest.fixture
def app_driver(main_window, qtbot):
    """A :class:`AppDriver` wrapping the live window.

    All knowledge of how to drive the UI (which widget edits which field, how a
    tab is opened, how an issue is activated) lives in the driver, so a UI
    refactor updates one file rather than every workflow test.
    """
    from ui_driver import AppDriver

    return AppDriver(main_window, qtbot)

