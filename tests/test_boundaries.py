"""Architectural boundary tests.

The ``core`` and ``state`` layers must remain frontend-agnostic: they must not
import any UI framework, and ``core`` must not depend on frontend or state
packages.
"""

from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# Known UI-framework packages that must never appear in the frontend-agnostic
# layers.  Extend this list if additional frameworks are ever evaluated.
_FRONTEND_FRAMEWORK_IMPORTS = (
    "import PySide6",
    "from PySide6",
    "import PyQt",
    "from PyQt",
    "import tkinter",
    "from tkinter",
    "import wx",
    "from wx ",
    "import gi",
    "from gi ",
)


def _python_files(*subdirs: str) -> list[Path]:
    files: list[Path] = []
    for subdir in subdirs:
        files.extend((APP_DIR / subdir).rglob("*.py"))
    return files


def test_core_and_state_have_no_ui_framework_imports():
    """core/ and state/ must not import any UI framework."""
    offenders: list[tuple[str, str]] = []
    for path in _python_files("core", "state"):
        text = path.read_text("utf-8")
        offenders.extend((path.name, pattern) for pattern in _FRONTEND_FRAMEWORK_IMPORTS if pattern in text)
    assert not offenders, f"UI-framework import found in frontend-agnostic layer: {offenders}"


def test_core_does_not_import_frontend_or_state():
    offenders = []
    for path in _python_files("core"):
        text = path.read_text("utf-8")
        if "import ui_qt" in text or "from ui_qt" in text:
            offenders.append((path.name, "ui_qt"))
        if "import state" in text or "from state" in text:
            offenders.append((path.name, "state"))
    assert not offenders, f"core must not depend on ui_qt/state: {offenders}"


def test_dialog_filters_derive_from_the_loader_s_own_extension_list():
    """One source of truth: a dialog can never offer a format the loader
    does not read, or hide one it does."""
    from core.bpx_gateway import SUPPORTED_EXTENSIONS
    from ui_qt.file_filters import BPX_FILTER, BPX_FILTER_WITH_ALL, export_filter

    for extension in SUPPORTED_EXTENSIONS:
        assert f"*{extension}" in BPX_FILTER
        assert f"*{extension}" in BPX_FILTER_WITH_ALL
    assert export_filter("yaml") == "YAML (*.yaml *.yml)"
    assert export_filter("json") == "JSON (*.json)"


def test_no_module_spells_the_bpx_extension_list_out_by_hand():
    """The five hand-written copies of the filter string are what
    ``ui_qt/file_filters.py`` exists to prevent coming back."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if path.name != "file_filters.py" and "*.json *.yaml *.yml" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
