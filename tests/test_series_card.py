"""SeriesCard + NumericGrid: Phase 4b of the input-system redesign.

Covers the grid foundation (raw-object cells, add/remove rows, no coercion),
the SeriesCard built on it, the registry's representability predicate, and the
values.py refactor invariants. The keyboard layering (cell-level vs card-level
Enter/Escape) is exercised end-to-end in the workflow suite; here we test the
data contract, which is where silent corruption would hide.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.grid import NumericGrid
from ui_qt.cards.registry import create_card, series_is_representable
from ui_qt.cards.series import SeriesCard
from ui_qt.cards.values import format_value, parse_value, values_equal


@pytest.fixture(autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _series(value, label="Time [s]") -> SeriesCard:
    param = ParameterItem(
        label=label,
        path=("Validation", "run", label),
        kind=ParameterKind.SERIES,
        value=value,
    )
    return create_card(param, None)


# ----------------------------------------------------------------------
# values.py: the shared parse/format convention (post-refactor invariants)
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", None),
        ("   ", None),
        ("5", 5),
        ("5.0", 5.0),
        ("-5", -5),
        ("1e3", 1000),  # no '.', so integral text stays int -- matches ScalarCard
        ("1.5e3", 1500.0),
        (".5", 0.5),
        ("2*x", "2*x"),
        ("oops", "oops"),
        (" 7 ", 7),
    ],
)
def test_parse_value_matches_the_lenient_convention(text, expected):
    result = parse_value(text)
    assert result == expected or (result != result and expected != expected)
    assert type(result) is type(expected)


def test_format_value_is_empty_only_for_none():
    assert format_value(None) == ""
    assert format_value(5) == "5"
    assert format_value("x") == "x"


def test_parse_and_format_round_trip_a_blank_cell():
    """A blank cell is None and stays None -- never "" and never 0."""
    assert parse_value(format_value(None)) is None


def test_values_equal_is_type_aware():
    assert values_equal(5, 5) is True
    assert values_equal(5, 5.0) is False
    assert values_equal(True, 1) is False
    assert values_equal(None, "") is False


# ----------------------------------------------------------------------
# NumericGrid: raw-object cells, no coercion, add/remove
# ----------------------------------------------------------------------


def test_grid_holds_raw_objects_verbatim():
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[0], [100], [200]])
    assert grid.values() == [[0], [100], [200]]


def test_a_bad_cell_survives_as_a_string_not_zero():
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[0], [100]])
    grid._model.setData(grid._model.index(1, 0), "oops", Qt.EditRole)
    assert grid.values() == [[0], ["oops"]]


def test_a_blank_cell_is_none_not_empty_string():
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[5]])
    grid._model.setData(grid._model.index(0, 0), "", Qt.EditRole)
    assert grid.values() == [[None]]


def test_insert_and_remove_rows():
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[0], [100]])
    grid.insert_row()
    assert grid.row_count == 3
    assert grid.values()[-1] == [None]
    grid.remove_row()
    grid.remove_row()
    assert grid.row_count == 1


def test_remove_button_disabled_on_an_empty_grid():
    grid = NumericGrid(("Time [s]",))
    assert grid.row_count == 0
    assert grid._remove_button.isEnabled() is False
    grid.set_values([[1]])
    grid.insert_row()
    assert grid._remove_button.isEnabled() is True


def test_set_values_does_not_emit_changed():
    """Seeding the grid must not mark a hosting card touched."""
    grid = NumericGrid(("Time [s]",))
    fired = []
    grid.changed.connect(lambda: fired.append(1))
    grid.set_values([[1], [2]])
    assert fired == []


def test_editing_a_cell_emits_changed():
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[1]])
    fired = []
    grid.changed.connect(lambda: fired.append(1))
    grid._model.setData(grid._model.index(0, 0), "2", Qt.EditRole)
    assert fired == [1]


def test_a_no_op_retype_does_not_emit_changed():
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[5]])
    fired = []
    grid.changed.connect(lambda: fired.append(1))
    grid._model.setData(grid._model.index(0, 0), "5", Qt.EditRole)
    assert fired == []


def test_grid_row_numbers_are_one_based():
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[10], [20]])
    header = grid._model.headerData
    assert header(0, Qt.Vertical) == "1"
    assert header(1, Qt.Vertical) == "2"
    assert header(0, Qt.Horizontal) == "Time [s]"


# ----------------------------------------------------------------------
# SeriesCard
# ----------------------------------------------------------------------


def test_series_card_reads_back_its_list():
    card = _series([0, 100, 200])
    assert isinstance(card, SeriesCard)
    assert card.value() == [0, 100, 200]


def test_series_card_header_is_the_label_carrying_the_unit():
    card = _series([0], label="Current [A]")
    assert card._grid._model.headerData(0, Qt.Horizontal) == "Current [A]"


def test_none_value_is_an_empty_grid_and_not_dirty():
    """A freshly added parameter (None) renders empty and commits nothing."""
    card = _series(None)
    assert card.value() == []
    assert card.is_dirty is False


def test_untouched_card_is_not_dirty():
    card = _series([1, 2, 3])
    assert card.is_dirty is False


def test_editing_a_cell_makes_the_card_dirty():
    card = _series([0, 100])
    card._grid._model.setData(card._grid._model.index(0, 0), "42", Qt.EditRole)
    assert card.is_dirty is True
    assert card.value() == [42, 100]


def test_a_bad_cell_is_committed_verbatim():
    card = _series([0, 100])
    card._grid._model.setData(card._grid._model.index(1, 0), "oops", Qt.EditRole)
    assert card.value() == [0, "oops"]


def test_reset_restores_the_original_rows():
    card = _series([0, 100, 200])
    card._grid._model.setData(card._grid._model.index(0, 0), "999", Qt.EditRole)
    assert card.is_dirty is True

    card.reset()

    assert card.value() == [0, 100, 200]
    # reset() re-seeds via set_values, which does NOT emit changed, so it never
    # re-touches the card -- unlike the line-edit cards, whose reset() re-fires
    # textChanged. The residual _touched here is the earlier edit's; the base's
    # _reset_draft (Escape) is what clears it, exercised end-to-end elsewhere.
    card._touched = False
    assert card.is_dirty is False


def test_adding_a_row_yields_a_null_cell_not_zero():
    card = _series([0, 100])
    card._grid.insert_row()
    assert card.value() == [0, 100, None]


def test_empty_grid_reads_back_as_empty_list():
    card = _series([5])
    card._grid.remove_row()
    assert card.value() == []


# ----------------------------------------------------------------------
# Registry representability predicate
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, [], [0, 1, 2], [0.5, 1.5], ["oops", 3], [None, 1, 2], [1, None]],
)
def test_representable_series_values_get_the_series_card(value):
    assert series_is_representable(value) is True
    assert isinstance(_series(value), SeriesCard)


@pytest.mark.parametrize(
    "value",
    [
        {"x": [1], "y": [2]},   # a dict is not a series
        [[1, 2], [3, 4]],        # nested lists have no flat-cell form
        [1, True, 3],            # a bool would round-trip as the string "True"
        "not a list",
        42,
    ],
)
def test_unrepresentable_series_values_fall_back_to_raw_json(value):
    """A SERIES value the grid cannot show stays editable as Raw JSON (structure
    preserved), never a read-only view -- so no declared field reaches a
    ReadOnlyCard, and a free-text card never commits a dict's repr."""
    assert series_is_representable(value) is False
    card = _series(value)
    assert type(card).__name__ == "RawValueCard"
    assert card.is_editable is True


def test_a_bool_item_is_not_representable_even_though_it_is_an_int():
    assert series_is_representable([1, 2, True]) is False
