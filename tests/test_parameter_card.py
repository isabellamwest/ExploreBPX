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
from PySide6.QtWidgets import QApplication, QLabel

from pathlib import Path

from core import bpx_gateway
from core.compare import ValueGroup
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from state.reference_snapshot import ReferenceSnapshot
from ui_qt import style
from ui_qt.cards.parameter_card import ParameterCard
from ui_qt.cards.reference_block import _monospace_font
from ui_qt.cards.table_preview import charts_available
from ui_qt.reference_identity import build_pins


def _pins(count: int = 1):
    """ReferencePins with no comparisons -- the ledger tests below hand the
    card ready-made ValueGroups, so only identity (letters/colours) is
    exercised here."""
    names = ("alpha.json", "bravo.json", "charlie.json", "delta.json")[:count]
    snapshots = [
        ReferenceSnapshot(
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
        for name in names
    ]
    return build_pins(snapshots, [])


def _group(value, *, indices=(0,), same: bool = False) -> ValueGroup:
    return ValueGroup(indices=tuple(indices), value=value, equals_main=same)


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


def test_description_sits_directly_under_title_with_reference_pinned():
    """Pinning a reference must not move the description: it stays directly
    under the title in the header block, and the new "Main" role label
    joins the editor's own row (aligned-rows layout), not the header."""
    card = _series_card_with_description()
    card.set_reference_groups((_group([1, 2, 3]),), _pins(1))
    description = card.findChild(QLabel, "CardDescription")
    header_box = description.parentWidget().layout()
    desc_index = _layout_index(header_box, description)
    expected_desc_index = 2 if card._rename_row is not None else 1
    assert desc_index == expected_desc_index
    assert desc_index == header_box.count() - 1  # the label never joined it
    assert _layout_index(card._value_row, card._main_file_heading) == 0
    assert _layout_index(card._value_row, card._editor) == 1


def test_headings_absent_with_no_reference_pinned():
    """The plain card (no ``set_reference_groups`` call at all) carries no
    "Main" role label and no ledger -- exactly today's card."""
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    assert card._main_file_heading is None
    assert card._reference_ledger is None


def test_headings_present_only_while_a_pin_has_the_key():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference_groups((_group(2.0),), _pins(1))
    assert card._main_file_heading is not None and not card._main_file_heading.isHidden()
    assert card._reference_ledger is not None and not card._reference_ledger.isHidden()

    card.set_reference_groups((), _pins(1))
    assert card._main_file_heading.isHidden()
    assert card._reference_ledger.isHidden()


def test_ledger_row_shows_unit_for_scalar_kind():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"), unit="m2")
    card.set_reference_groups((_group(2.0),), _pins(1))
    row = card._reference_ledger._rows[0]
    assert row._unit_label is not None
    assert row._unit_label.text() == "m2"


def test_ledger_row_hides_unit_for_kinds_without_one():
    """SERIES (like TABLE/FUNCTION/BOOLEAN) has no unit label on its main
    editor, so the ledger row shows none either."""
    card = _series_card_with_description()
    card.set_reference_groups((_group([1, 2, 3]),), _pins(1))
    assert card._reference_ledger._rows[0]._unit_label is None


def test_ledger_row_stacks_one_badge_per_group_member():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference_groups((_group(2.0, indices=(0, 1)),), _pins(2))
    from PySide6.QtWidgets import QLabel as _QLabel

    row = card._reference_ledger._rows[0]
    badges = [b.text() for b in row.findChildren(_QLabel, "ReferenceBadge")]
    assert badges == ["Al", "Br"]


def test_clicking_pull_emits_the_group_without_dirtying_the_card():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    group = _group(2.0)
    card.set_reference_groups((group,), _pins(1))
    received: list = []
    card.pull_requested.connect(received.append)

    card._reference_ledger._rows[0]._pull.click()

    assert received == [group]
    assert not card.is_dirty


def test_equal_group_shows_same_and_no_pull():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference_groups((_group(1.0, same=True),), _pins(1))
    row = card._reference_ledger._rows[0]
    assert row._same_label is not None and row._same_label.text() == "same"
    assert row._pull is None


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
    card.set_reference_groups((_group(ref_value),), _pins(1))

    row = card._reference_ledger._rows[0]
    assert row._value is None
    assert row._grid is not None
    table = row._grid._table
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
    assert row._pull is not None

    if charts_available():
        preview = card._editor._table_body._preview
        assert preview._ref_points == [(0.0, 2.0), (1.0, 3.0), (5.0, 9.0)]
        assert not preview._legend.isHidden()


def test_equal_table_reference_keeps_the_compact_one_liner():
    value = {"x": [0, 1], "y": [2, 3]}
    card = _table_card(value)
    card.set_reference_groups((_group(dict(value), same=True),), _pins(1))

    row = card._reference_ledger._rows[0]
    assert row._grid is None
    assert row._value is not None
    assert row._value.text() == "table · 2 points"
    assert row._same_label is not None
    assert row._pull is None

    if charts_available():
        preview = card._editor._table_body._preview
        assert preview._ref_points == []
        assert preview._legend.isHidden()


@requires_charts
def test_undocking_the_reference_clears_the_table_overlay():
    card = _table_card({"x": [0, 1], "y": [2, 3]})
    card.set_reference_groups((_group({"x": [0, 5], "y": [2, 9]}),), _pins(1))
    preview = card._editor._table_body._preview
    assert preview._ref_points

    card.set_reference_groups((), [])

    assert preview._ref_points == []
    assert preview._legend.isHidden()


@requires_charts
def test_growing_the_grid_keeps_the_reference_section_and_its_overlay():
    """A grid growing into the page's leftover height is a resize, not a
    takeover: the reference section stays, and so does the chart overlay
    inside the editor that carries the comparison."""
    card = _table_card({"x": [0, 1], "y": [2, 3]})
    card.set_reference_groups((_group({"x": [0, 5], "y": [2, 9]}),), _pins(1))
    preview = card._editor._table_body._preview
    assert preview._ref_points

    card.growable_grid().set_fill_available(True)

    assert card._reference_ledger.isVisibleTo(card)
    assert preview._ref_points
    assert preview.isVisibleTo(card._editor)


def test_full_multiline_expression_reference_renders_in_full():
    card = _function_card("x + 1")
    long_expression = "1*x +\n2*x**2 +\n3*x**3"
    card.set_reference_groups((_group(long_expression),), _pins(1))

    row = card._reference_ledger._rows[0]
    assert row._value.text() == long_expression  # no "…" truncation
    assert row._value.font().family() == _monospace_font().family()


def test_non_expression_reference_never_gets_the_monospace_font():
    card = _card(("Parameterisation", "Cell", "Electrode area [m2]"))
    card.set_reference_groups((_group(2.0),), _pins(1))
    assert card._reference_ledger._rows[0]._value.font().family() != _monospace_font().family()


@requires_charts
def test_function_cards_table_overlay_survives_switching_mode_away_and_back():
    """FunctionCard's ``InterpolatedTable`` mode is one of several strip
    entries -- the overlay lives on that mode's own (always-alive) body, so
    switching the strip away and back must neither lose nor duplicate it."""
    card = _function_card({"x": [0, 1], "y": [2, 3]})  # opens on InterpolatedTable
    card.set_reference_groups((_group({"x": [0, 1, 9], "y": [2, 3, 50]}),), _pins(1))
    table_body = card._editor._table_body
    assert table_body._preview._ref_points == [(0.0, 2.0), (1.0, 3.0), (9.0, 50.0)]

    card._editor.select_mode("FloatInt")
    assert table_body._preview._ref_points == [(0.0, 2.0), (1.0, 3.0), (9.0, 50.0)]

    card._editor.select_mode("InterpolatedTable")
    assert table_body._preview._ref_points == [(0.0, 2.0), (1.0, 3.0), (9.0, 50.0)]
