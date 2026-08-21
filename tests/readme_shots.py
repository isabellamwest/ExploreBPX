"""Regenerate the README screenshots from the live app.

Not part of the test suite (the filename lacks the ``test_`` prefix, so
default discovery skips it). Run it explicitly, on the native platform so
real fonts and colours render:

    QT_QPA_PLATFORM=cocoa .venv/bin/python -m pytest tests/readme_shots.py -s

Screenshots land in ``docs/screenshots/`` at the window's device pixel
ratio. Every capture drives the real ``MainWindow`` through ``AppDriver``,
so the images can never drift from what the app actually does.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "screenshots"
PYBAMM_SETS = REPO_ROOT / "app" / "data" / "example_documents" / "pybamm"

WINDOW_SIZE = (1400, 880)
TOAST_GONE_MS = 4300  # Toast.DISMISS_DELAY_MS plus a settling margin


def _shoot(window, qtbot, name: str) -> None:
    qtbot.wait(600)  # let charts, badges and debounced validation settle
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(OUT_DIR / name))
    print(f"captured {name}")


def test_capture_main_document_views(app_driver, main_window, qtbot):
    """Editor / Source / Workspace around a rich, valid main document."""
    d = app_driver
    main_window.resize(*WINDOW_SIZE)
    main_window.show()
    qtbot.waitExposed(main_window)

    # The bundled Chen2020 reference set as the main document, with two
    # more sets docked as comparison references.
    d.open(PYBAMM_SETS / "chen2020.json")
    d.wait_for_live_validation()
    d.dock_library_reference("pybamm/prada2013")
    d.dock_library_reference("pybamm/ai2020")
    qtbot.wait(TOAST_GONE_MS)  # let the "Pinned …" toast dismiss itself

    d.show_view("Workspace")
    _shoot(main_window, qtbot, "workspace.png")

    d.show_view("Editor")
    d.go_to(("Parameterisation", "Negative electrode", "OCP [V]"))
    d.wait_for_live_validation()
    _shoot(main_window, qtbot, "editor.png")

    d.show_view("Source")
    _shoot(main_window, qtbot, "source.png")

    # A freshly scaffolded document: outstanding work, nothing invalid.
    d.show_view("Workspace")
    d.click_new_workspace()
    d.click_workspace_new("SPM")
    d.wait_for_live_validation()
    d.show_view("Diagnostics")
    _shoot(main_window, qtbot, "diagnostics_new.png")


def test_capture_invalid_document_views(app_driver, main_window, qtbot, fixtures_dir):
    """Diagnostics on a document the official validator rejects."""
    d = app_driver
    main_window.resize(*WINDOW_SIZE)
    main_window.show()
    qtbot.waitExposed(main_window)

    d.open(fixtures_dir / "invalid_blended_state_mismatch.json")
    d.wait_for_live_validation()
    qtbot.wait(TOAST_GONE_MS)  # a converted-copy toast may have appeared
    d.show_view("Diagnostics")
    _shoot(main_window, qtbot, "diagnostics_invalid.png")
