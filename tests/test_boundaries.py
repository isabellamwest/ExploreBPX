"""Architectural boundary tests.

The ``core`` and ``state`` layers must remain frontend-agnostic: no Streamlit
imports, and ``core`` must not depend on ``ui`` or ``state``.
"""

from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _python_files(*subdirs: str) -> list[Path]:
    files: list[Path] = []
    for subdir in subdirs:
        files.extend((APP_DIR / subdir).rglob("*.py"))
    return files


def test_core_and_state_have_no_streamlit():
    offenders = []
    for path in _python_files("core", "state"):
        text = path.read_text("utf-8")
        if "import streamlit" in text or "from streamlit" in text:
            offenders.append(path.name)
    assert not offenders, f"Streamlit imported in frontend-agnostic layer: {offenders}"


def test_core_does_not_import_ui_or_state():
    offenders = []
    for path in _python_files("core"):
        text = path.read_text("utf-8")
        if "import ui" in text or "from ui" in text:
            offenders.append((path.name, "ui"))
        if "import state" in text or "from state" in text:
            offenders.append((path.name, "state"))
    assert not offenders, f"core must not depend on ui/state: {offenders}"