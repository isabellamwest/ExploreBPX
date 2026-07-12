"""ParameterCard header: the parameter's symbol shows beside its name.

The symbol is verbatim from the technical-descriptions dataset (via
``resolve_parameter_metadata``); the card renders it as maths but invents
nothing. A parameter the dataset does not document simply shows no symbol.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from core import bpx_gateway
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.parameter_card import ParameterCard


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


def _card(path, kind=ParameterKind.SCALAR, value=1.0) -> ParameterCard:
    param = ParameterItem(label=path[-1], path=tuple(path), kind=kind, value=value)
    return ParameterCard(param, bpx_gateway.field_meta(tuple(path)))


def test_documented_parameter_shows_its_symbol():
    path = ("Parameterisation", "Cell", "Electrode area [m2]")
    card = _card(path)
    assert card._metadata.symbol == "A"
    symbols = card.findChildren(object, "CardSymbol")
    assert len(symbols) == 1


def test_undocumented_parameter_shows_no_symbol():
    """A user-defined parameter has no dataset entry, so no symbol is shown --
    the header is the title alone, nothing fabricated."""
    path = ("Parameterisation", "User-defined", "My custom thing")
    card = _card(path)
    assert card._metadata.symbol is None
    assert card.findChildren(object, "CardSymbol") == []


def _series_card_with_description() -> ParameterCard:
    param = ParameterItem(
        label="Time [s]",
        path=("Validation", "run", "Time [s]"),
        kind=ParameterKind.SERIES,
        value=[0, 1, 2],
        description="Time in seconds (list of FloatInts).",
    )
    return ParameterCard(param, None)


def test_description_hides_while_the_grid_is_expanded():
    """Expanding a grid takes over the pane; the description hides to make room
    (the preview chart above the grid stays), and returns on collapse."""
    card = _series_card_with_description()
    assert card._description_widgets  # a description block was built
    assert all(w.isVisibleTo(card) for w in card._description_widgets)

    card._editor.expand_toggled.emit(True)
    assert all(not w.isVisibleTo(card) for w in card._description_widgets)

    card._editor.expand_toggled.emit(False)
    assert all(w.isVisibleTo(card) for w in card._description_widgets)
