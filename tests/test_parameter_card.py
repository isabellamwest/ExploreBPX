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
from core.compare import RowState
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.parameter_card import ParameterCard


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


def _card(path, kind=ParameterKind.SCALAR, value=1.0, unit="") -> ParameterCard:
    param = ParameterItem(label=path[-1], path=tuple(path), kind=kind, value=value, unit=unit)
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


def _layout_index(layout, item) -> int:
    for i in range(layout.count()):
        entry = layout.itemAt(i)
        if entry.widget() is item or entry.layout() is item:
            return i
    raise AssertionError(f"{item!r} not found in layout")


def test_description_sits_directly_under_title_without_reference():
    """Multi-file track M3 restyle: the description is always directly below
    the title (and the rename row, when present), never below the editor.
    Structured-page layout: the description closes the header block, and the
    editor lives in the content column below it."""
    card = _series_card_with_description()
    description = card._description_widgets[0]
    header_frame = description.parentWidget()
    header_box = header_frame.layout()
    desc_index = _layout_index(header_box, description)
    expected_desc_index = 2 if card._rename_row is not None else 1
    assert desc_index == expected_desc_index
    assert desc_index == header_box.count() - 1  # nothing below it in the header
    # The whole header block precedes the content column holding the editor.
    body = card._body_layout.parentWidget()
    top = card.layout()
    assert _layout_index(top, header_frame) < _layout_index(top, body)


def test_description_sits_directly_under_title_with_reference_docked():
    """Docking a reference must not move the description: it stays directly
    under the title in the header block, and the new "Main file" heading
    slots in directly above the editor in the content column, not into the
    header."""
    card = _series_card_with_description()
    card.set_reference([1, 2, 3], RowState.DIFFERS, ParameterKind.SERIES)
    description = card._description_widgets[0]
    header_box = description.parentWidget().layout()
    desc_index = _layout_index(header_box, description)
    expected_desc_index = 2 if card._rename_row is not None else 1
    assert desc_index == expected_desc_index
    assert desc_index == header_box.count() - 1  # the heading never joined it
    main_heading_index = _layout_index(card._body_layout, card._main_file_heading)
    editor_index = _layout_index(card._body_layout, card._value_row)
    assert editor_index == main_heading_index + 1


def test_headings_absent_with_no_reference_docked():
    """The plain card (no ``set_reference`` call at all) carries no "Main
    file"/"Reference file" heading -- exactly today's card."""
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    assert card._main_file_heading is None
    assert card._reference_block is None


def test_headings_present_only_while_reference_docked():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference(2.0, RowState.DIFFERS, ParameterKind.SCALAR)
    assert card._main_file_heading is not None and not card._main_file_heading.isHidden()
    assert card._reference_block is not None and not card._reference_block.isHidden()

    card.set_reference(None, None, None)
    assert card._main_file_heading.isHidden()
    assert card._reference_block.isHidden()


def test_reference_row_shows_unit_for_scalar_kind():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"), unit="m2")
    card.set_reference(2.0, RowState.DIFFERS, ParameterKind.SCALAR)
    assert not card._reference_block._unit_label.isHidden()
    assert card._reference_block._unit_label.text() == "m2"


def test_reference_row_hides_unit_for_kinds_without_one():
    """SERIES (like TABLE/FUNCTION/BOOLEAN) has no unit label on its main
    editor, so the reference row shows none either."""
    card = _series_card_with_description()
    card.set_reference([1, 2, 3], RowState.DIFFERS, ParameterKind.SERIES)
    assert card._reference_block._unit_label.isHidden()


def test_clicking_copy_up_emits_signal_without_dirtying_the_card():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference(2.0, RowState.DIFFERS, ParameterKind.SCALAR)
    received: list = []
    card.copy_up_requested.connect(lambda: received.append(True))

    card._reference_block._copy_up.click()

    assert received == [True]
    assert not card.is_dirty
