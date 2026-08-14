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

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from explore_bpx.core import bpx_gateway
from explore_bpx.core.compare import ValueGroup
from explore_bpx.core.parameter_types import ParameterKind
from explore_bpx.core.tree_model import ParameterItem
from explore_bpx.state.reference_snapshot import ReferenceSnapshot
from explore_bpx.ui_qt import style
from explore_bpx.ui_qt.cards.parameter_card import ParameterCard
from explore_bpx.ui_qt.cards.reference_block import _monospace_font
from explore_bpx.ui_qt.cards.table_preview import charts_available
from explore_bpx.ui_qt.reference_identity import ReferencePin


@pytest.fixture(autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _card(path, kind=ParameterKind.SCALAR, value=1.0, unit="") -> ParameterCard:
    param = ParameterItem(label=path[-1], path=tuple(path), kind=kind, value=value, unit=unit)
    return ParameterCard(param, bpx_gateway.field_meta(tuple(path)))


def _pin(index: int = 0, name: str = "reference.json") -> ReferencePin:
    snapshot = ReferenceSnapshot(
        raw={},
        path=Path(name),
        filename=name,
        model="SPM",
        error_count=0,
        warning_count=0,
        section_count=0,
        parameter_count=0,
        mtime=0.0,
    )
    return ReferencePin(
        index=index,
        snapshot=snapshot,
        comparison=None,
        letters=name[:2].capitalize(),
        colour=style.REFERENCE_BADGES[index],
    )


def _one_reference(value, *, equals_main: bool = False):
    """The ``(groups, pins)`` pair ``set_reference`` takes for a single
    pinned reference sitting at *value*."""
    return (ValueGroup((0,), value, equals_main),), [_pin()]


def _row_badges(row) -> list[str]:
    cluster = row.findChild(QWidget, "LedgerBadgeCluster")
    return [child.text() for child in cluster.findChildren(QLabel)]


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


def test_description_stays_put_however_tall_the_grid_grows():
    """The description describes the parameter, so it never moves or hides:
    a grid growing into the page's leftover height takes that height from the
    white tail below, not from the header band."""
    card = _series_card_with_description()
    description = card.findChild(QLabel, "CardDescription")
    assert description is not None
    assert description.isVisibleTo(card)

    card.growable_grid().set_fill_available(True)

    assert description.isVisibleTo(card)


def test_a_grid_card_offers_its_grid_for_the_pages_leftover_height():
    """The Inspector reaches the editor's grid through the card -- a card with
    no grid (a scalar) offers nothing and keeps the page's white tail."""
    card = _series_card_with_description()
    assert card.growable_grid() is card._editor._grid


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
    description = card.findChild(QLabel, "CardDescription")
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
    card.set_reference(*_one_reference([1, 2, 3]), ParameterKind.SERIES)
    description = card.findChild(QLabel, "CardDescription")
    header_box = description.parentWidget().layout()
    desc_index = _layout_index(header_box, description)
    expected_desc_index = 2 if card._rename_row is not None else 1
    assert desc_index == expected_desc_index
    assert desc_index == header_box.count() - 1  # the label never joined it
    assert _layout_index(card._value_row, card._main_file_heading) == 0
    assert _layout_index(card._value_row, card._editor) == 1


def test_headings_absent_with_no_reference_docked():
    """The plain card (no ``set_reference`` call at all) carries no "Main"
    role label and no ledger -- exactly today's card."""
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    assert card._main_file_heading is None
    assert card._ledger is None


def test_headings_present_only_while_a_reference_is_pinned():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference(*_one_reference(2.0), ParameterKind.SCALAR)
    assert card._main_file_heading is not None
    assert not card._main_file_heading.isHidden()
    assert card._ledger is not None
    assert not card._ledger.isHidden()

    card.set_reference((), [], None)
    assert card._main_file_heading.isHidden()
    assert card._ledger.isHidden()


def test_ledger_groups_identical_values_into_one_row():
    """Three pinned references, two agreeing: two rows, and the agreeing
    pair's badges cluster on the row they share."""
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    pins = [_pin(0, "chen.json"), _pin(1, "marquis.json"), _pin(2, "okane.json")]
    groups = (ValueGroup((0, 2), 2.0, False), ValueGroup((1,), 3.0, False))

    card.set_reference(groups, pins, ParameterKind.SCALAR)

    assert len(card._ledger._rows) == 2
    assert _row_badges(card._ledger._rows[0]) == ["Ch", "Ok"]
    assert _row_badges(card._ledger._rows[1]) == ["Ma"]


def test_a_row_equal_to_main_says_same_and_offers_no_pull():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference(*_one_reference(1.0, equals_main=True), ParameterKind.SCALAR)

    row = card._ledger._rows[0]
    assert row.findChild(QPushButton, "PullButton") is None
    assert [label.text() for label in row.findChildren(QLabel) if label.objectName() == "LedgerSameLabel"] == ["same"]


def test_clicking_pull_names_the_first_pinned_source_and_does_not_dirty_the_card():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    pins = [_pin(0, "chen.json"), _pin(1, "marquis.json")]
    card.set_reference((ValueGroup((1, 0), 2.0, False),), pins, ParameterKind.SCALAR)
    received: list = []
    card.pull_requested.connect(received.append)

    card._ledger._rows[0].findChild(QPushButton, "PullButton").click()

    # The group's *first-pinned* member, not the first index listed.
    assert received == [1]
    assert not card.is_dirty


# ----------------------------------------------------------------------
# Richer table/function reference comparison
# ----------------------------------------------------------------------

requires_charts = pytest.mark.skipif(not charts_available(), reason="QtCharts not available in this PySide6 build")


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
    card.set_reference(*_one_reference(ref_value), ParameterKind.TABLE)

    ledger = card._ledger
    # The ledger row keeps the one-line summary; the numbers live in the
    # grid beneath it, badge-labelled with the pin they came from.
    assert ledger._rows[0]._value.text() == "table · 3 points"
    assert ledger._rows[0].findChild(QPushButton, "PullButton").isEnabled()
    assert not ledger._table_grid.isHidden()
    assert not ledger._grid_caption.isHidden()
    table = ledger._table_grid._table
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

    if charts_available():
        preview = card._editor._table_body._preview
        assert preview._curve_points == [[(0.0, 2.0), (1.0, 3.0), (5.0, 9.0)]]
        assert not preview._legend.isHidden()


def test_equal_table_reference_keeps_the_compact_one_liner():
    value = {"x": [0, 1], "y": [2, 3]}
    card = _table_card(value)
    card.set_reference(*_one_reference(dict(value), equals_main=True), ParameterKind.TABLE)

    ledger = card._ledger
    assert ledger._table_grid.isHidden()
    assert ledger._grid_caption.isHidden()
    assert ledger._rows[0]._value.text() == "table · 2 points"
    assert ledger._rows[0].findChild(QPushButton, "PullButton") is None

    if charts_available():
        preview = card._editor._table_body._preview
        assert preview._curve_points == []
        assert preview._legend.isHidden()


@requires_charts
def test_undocking_the_reference_clears_the_table_overlay():
    card = _table_card({"x": [0, 1], "y": [2, 3]})
    card.set_reference(*_one_reference({"x": [0, 5], "y": [2, 9]}), ParameterKind.TABLE)
    preview = card._editor._table_body._preview
    assert preview._curve_points

    card.set_reference((), [], None)

    assert preview._curve_points == []
    assert preview._legend.isHidden()


@requires_charts
def test_growing_the_grid_keeps_the_reference_section_and_its_overlay():
    """A grid growing into the page's leftover height is a resize, not a
    takeover: the reference section stays, and so does the chart overlay
    inside the editor that carries the comparison."""
    card = _table_card({"x": [0, 1], "y": [2, 3]})
    card.set_reference(*_one_reference({"x": [0, 5], "y": [2, 9]}), ParameterKind.TABLE)
    preview = card._editor._table_body._preview
    assert preview._curve_points

    card.growable_grid().set_fill_available(True)

    assert card._ledger.isVisibleTo(card)
    assert preview._curve_points
    assert preview.isVisibleTo(card._editor)


def test_full_multiline_expression_reference_renders_in_full():
    card = _function_card("x + 1")
    long_expression = "1*x +\n2*x**2 +\n3*x**3"
    card.set_reference(*_one_reference(long_expression), ParameterKind.FUNCTION)

    value = card._ledger._rows[0]._value
    assert value.text() == long_expression  # no "…" truncation
    assert value.font().family() == _monospace_font().family()


def test_non_expression_reference_never_gets_the_monospace_font():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference(*_one_reference(2.0), ParameterKind.SCALAR)
    assert card._ledger._rows[0]._value.font().family() != _monospace_font().family()


# ----------------------------------------------------------------------
# Function-expression reference overlay (the chart preview's own overlay)
# ----------------------------------------------------------------------


def test_function_references_excludes_a_non_string_value():
    """A reference whose value at this key is not itself a function string
    (here, a table) is simply absent from the chart overlay -- the ledger
    above already shows it."""
    card = _function_card("2*x")
    groups = (ValueGroup((0,), {"x": [0, 1], "y": [1, 2]}, False),)
    assert card._function_references(groups, [_pin()]) == []


def test_function_references_excludes_a_value_equal_to_main():
    card = _function_card("2*x")
    groups = (ValueGroup((0,), "2*x", True),)
    assert card._function_references(groups, [_pin()]) == []


@requires_charts
def test_function_reference_overlays_the_expression_chart_as_a_named_series():
    card = _function_card("2*x")
    card.set_reference(*_one_reference("3*x"), ParameterKind.FUNCTION)

    body = card._editor._expression_body
    name, _colour, points = body._chart._series_meta["ref-0"]
    assert name == "reference.json"
    assert len(points) == 200


@requires_charts
def test_function_reference_overlay_resamples_on_domain_change():
    card = _function_card("2*x")
    card.set_reference(*_one_reference("3*x"), ParameterKind.FUNCTION)
    body = card._editor._expression_body

    body._domain_high_edit.setText("2")
    body._domain_high_edit.editingFinished.emit()

    xs = [x for x, _y in body._chart._series_meta["ref-0"][2]]
    assert max(xs) == pytest.approx(2.0)


@requires_charts
def test_undocking_the_reference_clears_the_function_overlay():
    card = _function_card("2*x")
    card.set_reference(*_one_reference("3*x"), ParameterKind.FUNCTION)
    body = card._editor._expression_body
    assert "ref-0" in body._chart._series_meta

    card.set_reference((), [], None)

    assert "ref-0" not in body._chart._series_meta


@requires_charts
def test_function_cards_table_overlay_survives_switching_mode_away_and_back():
    """FunctionCard's ``InterpolatedTable`` mode is one of several strip
    entries -- the overlay lives on that mode's own (always-alive) body, so
    switching the strip away and back must neither lose nor duplicate it."""
    card = _function_card({"x": [0, 1], "y": [2, 3]})  # opens on InterpolatedTable
    card.set_reference(*_one_reference({"x": [0, 1, 9], "y": [2, 3, 50]}), ParameterKind.FUNCTION)
    table_body = card._editor._table_body
    assert table_body._preview._curve_points == [[(0.0, 2.0), (1.0, 3.0), (9.0, 50.0)]]

    card._editor.select_mode("FloatInt")
    assert table_body._preview._curve_points == [[(0.0, 2.0), (1.0, 3.0), (9.0, 50.0)]]

    card._editor.select_mode("InterpolatedTable")
    assert table_body._preview._curve_points == [[(0.0, 2.0), (1.0, 3.0), (9.0, 50.0)]]
