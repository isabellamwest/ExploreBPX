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
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def valid_spm_path() -> Path:
    return FIXTURES_DIR / "spm_example_valid.json"


@pytest.fixture
def valid_spm_bytes() -> bytes:
    return (FIXTURES_DIR / "spm_example_valid.json").read_bytes()


@pytest.fixture
def valid_spm_dict() -> dict:
    import json

    return json.loads((FIXTURES_DIR / "spm_example_valid.json").read_text("utf-8"))


@pytest.fixture
def spm_with_validation_path(valid_spm_dict, tmp_path) -> Path:
    """A valid SPM document with a Validation experiment (four SERIES arrays).

    The tracked SPM fixture has no Validation section, and every NMC/LFP fixture
    with one fails validation on unrelated moved-field errors that short-circuit
    the validator before it reaches the arrays. A SeriesCard test needs a
    document that is *valid* and *has* a series, so it can prove that editing a
    cell is what turns the badge invalid.
    """
    import json

    doc = dict(valid_spm_dict)
    doc["Validation"] = {
        "C/20 discharge": {
            "Time [s]": [0, 100, 200],
            "Current [A]": [-0.6, -0.6, -0.6],
            "Voltage [V]": [4.1, 4.0, 3.9],
            "Temperature [K]": [298.15, 298.15, 298.15],
        }
    }
    work = tmp_path / "spm_with_validation.json"
    work.write_text(json.dumps(doc), encoding="utf-8")
    return work


@pytest.fixture
def spm_with_ragged_table_path(valid_spm_dict, tmp_path) -> Path:
    """An SPM document whose Diffusivity holds a *ragged* interpolated table.

    ``{"x": [0, 1], "y": [1]}`` is a legal JSON value that no structured mode
    can represent -- a grid is rectangular, and padding it would invent a data
    point -- so ``FunctionCard`` must open it in ``Raw``. Used to exercise the
    Raw editor's commit gate against a real document.
    """
    import json

    doc = dict(valid_spm_dict)
    doc["Parameterisation"]["Negative electrode"]["Diffusivity [m2.s-1]"] = {
        "x": [0, 1],
        "y": [1],
    }
    work = tmp_path / "spm_ragged_table.json"
    work.write_text(json.dumps(doc), encoding="utf-8")
    return work


@pytest.fixture
def invalid_bpx_path() -> Path:
    """A fixture file that opens successfully but fails BPX validation."""
    return FIXTURES_DIR / "invalid_blended_state_mismatch.json"


@pytest.fixture
def warning_only_bpx_path() -> Path:
    """A fixture file that is valid but emits a warning-severity issue."""
    return FIXTURES_DIR / "warning_legacy_bpx_float.json"


@pytest.fixture
def spm_workfile(valid_spm_path, tmp_path) -> Path:
    """A writable copy of the valid SPM fixture.

    Using a copy keeps a session's ``backing_file`` off the repository fixture
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
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from ui_qt.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    yield window

    # The app's transient popups (search results, add-parameter, parameter
    # info) are floating `Qt.FramelessWindowHint | Qt.Tool` top-level
    # windows merely *parented* to a panel for lifetime -- they do not
    # cascade-hide/close with their parent. A test that opens one and
    # forgets to close it leaves it visible after `qtbot.addWidget` teardown
    # closes `window`, because `.close()` + `.deleteLater()` +
    # `processEvents()` never delivers `QEvent.DeferredDelete`, so the
    # popup's `OutsideDismissFilter` -- installed on the shared
    # `QApplication` -- stays registered and swallows the *next* test's
    # first outside click. Explicitly hide every other top-level widget so
    # each test starts with a clean `qApp`: hiding is what the filter
    # actually watches for (`QEvent.Hide`) to deregister itself.
    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            if widget is not window and widget.isVisible():
                widget.hide()
        app.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture
def app_driver(main_window, qtbot):
    """A :class:`AppDriver` wrapping the live window.

    All knowledge of how to drive the UI (which widget edits which field, how a
    tab is opened, how an issue is activated) lives in the driver, so a UI
    refactor updates one file rather than every workflow test.
    """
    from ui_driver import AppDriver

    return AppDriver(main_window, qtbot)

