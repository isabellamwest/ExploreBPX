"""Card registry contract: every editable parameter kind gets an editable card.

The important behaviour is that no editable kind ever falls back to a read-only
card (which would trap the user with a visible-but-uneditable value). We assert
the ``is_editable`` contract rather than concrete card classes, so the registry
can be reorganised without breaking these tests.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.registry import create_card


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "kind, value",
    [
        (ParameterKind.SCALAR, 1.0),
        (ParameterKind.INTEGER, 3),
        (ParameterKind.ENUM, "SPM"),
        (ParameterKind.FUNCTION, "not-a-function"),
    ],
)
def test_editable_kinds_produce_editable_cards(kind, value):
    """Editable kinds never fall back to a read-only card, even for an invalid
    stored value -- otherwise the user could not repair it."""
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=kind, value=value)
    card = create_card(param, None)
    assert card.is_editable


def test_unknown_kind_falls_back_to_read_only():
    """A kind with no editor (tables/unknown) is presented read-only."""
    _app()
    param = ParameterItem(
        label="T", path=("Header", "T"), kind=ParameterKind.TABLE, value={}
    )
    card = create_card(param, None)
    assert card.is_editable is False
