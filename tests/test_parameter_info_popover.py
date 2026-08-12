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
    # Unpopulated categories (e.g. the Symbol row) never appear.
    assert "Symbol" not in labels


def test_no_populated_fields_renders_nothing(qtbot):
    _app()
    popover = ParameterInfoPopover()
    qtbot.addWidget(popover)
    popover.show_metadata(ParameterMetadata())
    assert popover._layout.count() == 0


def test_custom_parameter_says_custom(qtbot):
    """A custom parameter's popover states its provenance rather than showing
    an empty glance."""
    _app()
    popover = ParameterInfoPopover()
    qtbot.addWidget(popover)
    popover.show_metadata(ParameterMetadata(is_custom=True))
    labels = [
        popover._layout.itemAt(i).widget().text() for i in range(popover._layout.count())
    ]
    assert "Custom parameter" in labels
    assert any("Not defined by the BPX schema" in text for text in labels)


def test_symbol_link_and_docs_hint_render_when_populated(qtbot):
    _app()
    popover = ParameterInfoPopover()
    qtbot.addWidget(popover)
    popover.show_metadata(
        ParameterMetadata(
            symbol=r"N_\mathrm{p}",
            specification_link="https://w3id.org/example",
            documentation=(("Physical correspondence", "Long prose."),),
        )
    )
    widgets = [
        popover._layout.itemAt(i).widget() for i in range(popover._layout.count())
    ]
    texts = [w.text() for w in widgets]
    assert "Symbol" in texts
    assert any("w3id.org/example" in t for t in texts)
    assert any("Documentation section" in t for t in texts)
    # The long-form prose itself must NOT render in the glance popover.
    assert not any("Long prose." in t for t in texts)
    # The symbol renders as a pixmap (matplotlib present), not as raw LaTeX.
    symbol_row = widgets[texts.index("Symbol") + 1]
    assert not symbol_row.pixmap().isNull()


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
    yield c
    # The popover is a floating Qt.Tool window parented (for lifetime, not
    # stacking) to the card, so closing the card alone would not close it and
    # a test that leaves it open would otherwise leak its application-level
    # OutsideDismissFilter registration into later tests in the same session.
    if c._popover is not None:
        c._popover.close()


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


def test_custom_parameter_card_popover_says_custom(qtbot):
    """A card built without FieldMeta (a user-authored parameter) surfaces
    "Custom parameter" through the real ( i ) button -- the everywhere path."""
    _app()
    parameter = ParameterItem(
        label="k_sei",
        path=("Parameterisation", "User-defined", "Ageing model", "k_sei"),
        kind=ParameterKind.SCALAR,
        value=1e-14,
    )
    c = ParameterCard(parameter, None)  # no schema metadata -> custom
    qtbot.addWidget(c)
    qtbot.mouseClick(c._info_button, Qt.LeftButton)
    labels = [
        c._popover._layout.itemAt(i).widget().text()
        for i in range(c._popover._layout.count())
    ]
    assert "Custom parameter" in labels
    if c._popover is not None:
        c._popover.close()


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


def test_outside_click_closes_popover_and_is_swallowed(card, qtbot):
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtWidgets import QApplication, QPushButton

    qtbot.mouseClick(card._info_button, Qt.LeftButton)
    assert card._popover.isVisible()

    decoy = QPushButton()
    decoy.setGeometry(2000, 2000, 50, 20)
    qtbot.addWidget(decoy)
    decoy.show()
    clicks = []
    decoy.clicked.connect(lambda: clicks.append(1))

    global_pos = decoy.mapToGlobal(decoy.rect().center())
    press = QMouseEvent(
        QEvent.MouseButtonPress, QPointF(decoy.rect().center()), QPointF(global_pos),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )
    QApplication.instance().sendEvent(decoy, press)

    assert card._popover.isVisible() is False
    # The dismissing press was swallowed: the button beneath never saw it.
    release = QMouseEvent(
        QEvent.MouseButtonRelease, QPointF(decoy.rect().center()), QPointF(global_pos),
        Qt.LeftButton, Qt.NoButton, Qt.NoModifier,
    )
    QApplication.instance().sendEvent(decoy, release)
    assert clicks == []
