"""Tests for the ( i ) parameter-information popover and its ParameterCard wiring.

Covers the popover's own rendering contract (only populated ``ParameterMetadata``
fields appear) and the card-level toggle/dismiss behaviour required by roadmap
2.4 sub-step 2: opened by the ( i ) button, dismissed by a second ( i ) click or
Escape.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.bpx_gateway import FieldMeta
from core.parameter_metadata import ParameterMetadata
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.parameter_card import ParameterCard
from ui_qt.parameter_info_popover import ParameterInfoPopover


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# ParameterInfoPopover rendering
# ---------------------------------------------------------------------------

def test_only_populated_fields_are_rendered(qtbot):
    _app()
    popover = ParameterInfoPopover()
    qtbot.addWidget(popover)
    popover.show_metadata(
        ParameterMetadata(physical_meaning="The ambient temperature.", units="K")
    )
    labels = [
        popover._layout.itemAt(i).widget().text() for i in range(popover._layout.count())
    ]
    assert "Physical meaning" in labels
    assert "The ambient temperature." in labels
    assert "Units" in labels
    assert "K" in labels
    # Unpopulated categories (e.g. Symbols) never appear.
    assert "Symbols" not in labels


def test_no_populated_fields_renders_nothing(qtbot):
    _app()
    popover = ParameterInfoPopover()
    qtbot.addWidget(popover)
    popover.show_metadata(ParameterMetadata())
    assert popover._layout.count() == 0


def test_escape_hides_popover(qtbot):
    _app()
    popover = ParameterInfoPopover()
    qtbot.addWidget(popover)
    popover.show_metadata(ParameterMetadata(physical_meaning="x"))
    popover.show()
    assert popover.isVisible()
    qtbot.keyClick(popover, Qt.Key_Escape)
    assert popover.isVisible() is False


# ---------------------------------------------------------------------------
# ParameterCard integration: the ( i ) button toggles the popover
# ---------------------------------------------------------------------------

@pytest.fixture
def card(qtbot):
    _app()
    parameter = ParameterItem(
        label="Ambient temperature [K]",
        path=("Header", "Ambient temperature [K]"),
        kind=ParameterKind.SCALAR,
        value=298.15,
    )
    meta = FieldMeta(alias="Ambient temperature [K]", description="The ambient temperature.")
    c = ParameterCard(parameter, meta)
    qtbot.addWidget(c)
    return c


def test_info_button_present_on_every_card(card):
    assert card._info_button.text() == "i"


def test_click_opens_popover_with_field_meta_content(card, qtbot):
    qtbot.mouseClick(card._info_button, Qt.LeftButton)
    assert card._popover is not None
    assert card._popover.isVisible()
    labels = [
        card._popover._layout.itemAt(i).widget().text()
        for i in range(card._popover._layout.count())
    ]
    assert "The ambient temperature." in labels
    assert "K" in labels


def test_second_click_closes_popover(card, qtbot):
    qtbot.mouseClick(card._info_button, Qt.LeftButton)
    assert card._popover.isVisible()
    qtbot.mouseClick(card._info_button, Qt.LeftButton)
    assert card._popover.isVisible() is False


def test_escape_closes_popover_opened_from_card(card, qtbot):
    qtbot.mouseClick(card._info_button, Qt.LeftButton)
    assert card._popover.isVisible()
    qtbot.keyClick(card._popover, Qt.Key_Escape)
    assert card._popover.isVisible() is False
