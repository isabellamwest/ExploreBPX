"""Shared pytest fixtures and import path setup.

Adds the ``app`` directory to ``sys.path`` so the project packages import the
same way they do when the application is launched from the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

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
