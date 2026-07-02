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
        for pattern in _FRONTEND_FRAMEWORK_IMPORTS:
            if pattern in text:
                offenders.append((path.name, pattern))
    assert not offenders, (
        f"UI-framework import found in frontend-agnostic layer: {offenders}"
    )


def test_core_does_not_import_frontend_or_state():
    offenders = []
    for path in _python_files("core"):
        text = path.read_text("utf-8")
        if "import ui_qt" in text or "from ui_qt" in text:
            offenders.append((path.name, "ui_qt"))
        if "import state" in text or "from state" in text:
            offenders.append((path.name, "state"))
    assert not offenders, f"core must not depend on ui_qt/state: {offenders}"