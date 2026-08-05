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

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from core import bpx_gateway
from core.compare import RowState
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt import style
from ui_qt.cards.parameter_card import ParameterCard
from ui_qt.cards.reference_block import _monospace_font
from ui_qt.cards.table_preview import charts_available


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
    under the title in the header block, and the new "Main" role label
    joins the editor's own row (aligned-rows layout), not the header."""
    card = _series_card_with_description()
    card.set_reference([1, 2, 3], RowState.DIFFERS, ParameterKind.SERIES)
    description = card._description_widgets[0]
    header_box = description.parentWidget().layout()
    desc_index = _layout_index(header_box, description)
    expected_desc_index = 2 if card._rename_row is not None else 1
    assert desc_index == expected_desc_index
    assert desc_index == header_box.count() - 1  # the label never joined it
    assert _layout_index(card._value_row, card._main_file_heading) == 0
    assert _layout_index(card._value_row, card._editor) == 1


def test_headings_absent_with_no_reference_docked():
    """The plain card (no ``set_reference`` call at all) carries no
    "Main"/"Reference" role label -- exactly today's card."""
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


# ----------------------------------------------------------------------
# Richer table/function reference comparison
# ----------------------------------------------------------------------

requires_charts = pytest.mark.skipif(
    not charts_available(), reason="QtCharts not available in this PySide6 build"
)


def _table_card(value) -> ParameterCard:
    param = ParameterItem(
        label="Custom table",
        path=("Parameterisation", "User-defined", "Custom table"),
        kind=ParameterKind.TABLE,
        value=value,
    )
    return ParameterCard(param, None)


def _function_card(value) -> ParameterCard:
    param = ParameterItem(
        label="OCP [V]",
        path=("Parameterisation", "Negative electrode", "OCP [V]"),
        kind=ParameterKind.FUNCTION,
        value=value,
    )
    return ParameterCard(param, None)


def test_differing_table_reference_shows_grid_with_diff_marks_and_overlay():
    card = _table_card({"x": [0, 1], "y": [2, 3]})
    ref_value = {"x": [0, 1, 5], "y": [2, 3, 9]}
    card.set_reference(ref_value, RowState.DIFFERS, ParameterKind.TABLE)

    block = card._reference_block
    assert block._value.isHidden()
    assert not block._table_grid.isHidden()
    table = block._table_grid._table
    assert table.rowCount() == 3
    # Rows (0, 2) and (1, 3) already exist in the main draft: quiet muted
    # text, so purple stays the mark of a genuinely differing row.
    muted = QColor(style.MUTED).name()
    assert table.item(0, 0).foreground().color().name() == muted
    assert table.item(1, 1).foreground().color().name() == muted
    # Row (5, 9) has no equal pair in main: reference purple, both cells.
    purple = QColor(style.REFERENCE).name()
    assert table.item(2, 0).foreground().color().name() == purple
    assert table.item(2, 1).foreground().color().name() == purple
    assert block._copy_up.isEnabled()

    if charts_available():
        preview = card._editor._table_body._preview
        assert preview._ref_points == [(0.0, 2.0), (1.0, 3.0), (5.0, 9.0)]
        assert not preview._legend.isHidden()


def test_equal_table_reference_keeps_the_compact_one_liner():
    value = {"x": [0, 1], "y": [2, 3]}
    card = _table_card(value)
    card.set_reference(dict(value), RowState.EQUAL, ParameterKind.TABLE)

    block = card._reference_block
    assert not block._value.isHidden()
    assert block._table_grid.isHidden()
    assert block._value.text() == "table · 2 points · same"
    assert not block._copy_up.isEnabled()

    if charts_available():
        preview = card._editor._table_body._preview
        assert preview._ref_points == []
        assert preview._legend.isHidden()


@requires_charts
def test_undocking_the_reference_clears_the_table_overlay():
    card = _table_card({"x": [0, 1], "y": [2, 3]})
    card.set_reference({"x": [0, 5], "y": [2, 9]}, RowState.DIFFERS, ParameterKind.TABLE)
    preview = card._editor._table_body._preview
    assert preview._ref_points

    card.set_reference(None, None, None)

    assert preview._ref_points == []
    assert preview._legend.isHidden()


@requires_charts
def test_expanding_the_grid_keeps_the_chart_overlay():
    """The reference *section* (grid + heading) hides while a grid takes
    over the pane (known Qt pitfall), but the chart overlay lives inside
    the editor itself and is untouched -- it carries the comparison while
    expanded."""
    card = _table_card({"x": [0, 1], "y": [2, 3]})
    card.set_reference({"x": [0, 5], "y": [2, 9]}, RowState.DIFFERS, ParameterKind.TABLE)
    preview = card._editor._table_body._preview
    assert preview._ref_points

    card._editor.expand_toggled.emit(True)

    assert not card._reference_block.isVisibleTo(card)
    assert preview._ref_points  # the overlay itself is never touched
    assert preview.isVisibleTo(card._editor)


def test_full_multiline_expression_reference_renders_in_full():
    card = _function_card("x + 1")
    long_expression = "1*x +\n2*x**2 +\n3*x**3"
    card.set_reference(long_expression, RowState.DIFFERS, ParameterKind.FUNCTION)

    block = card._reference_block
    assert block._value.text() == long_expression  # no "…" truncation
    assert block._value.font().family() == _monospace_font().family()


def test_non_expression_reference_never_gets_the_monospace_font():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference(2.0, RowState.DIFFERS, ParameterKind.SCALAR)
    assert card._reference_block._value.font().family() != _monospace_font().family()


@requires_charts
def test_function_cards_table_overlay_survives_switching_mode_away_and_back():
    """FunctionCard's ``InterpolatedTable`` mode is one of several strip
    entries -- the overlay lives on that mode's own (always-alive) body, so
    switching the strip away and back must neither lose nor duplicate it."""
    card = _function_card({"x": [0, 1], "y": [2, 3]})  # opens on InterpolatedTable
    card.set_reference({"x": [0, 1, 9], "y": [2, 3, 50]}, RowState.DIFFERS, ParameterKind.FUNCTION)
    table_body = card._editor._table_body
    assert table_body._preview._ref_points == [(0.0, 2.0), (1.0, 3.0), (9.0, 50.0)]

    card._editor.select_mode("FloatInt")
    assert table_body._preview._ref_points == [(0.0, 2.0), (1.0, 3.0), (9.0, 50.0)]

    card._editor.select_mode("InterpolatedTable")
    assert table_body._preview._ref_points == [(0.0, 2.0), (1.0, 3.0), (9.0, 50.0)]
