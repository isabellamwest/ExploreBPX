"""ModalCard + mode bodies: Phase 4c of the input-system redesign.

Covers the mode strip's construction-time decisions for a union-typed BPX
field (FunctionCard's FloatInt | Function | InterpolatedTable, plus a
conditional Raw mode): which mode a committed value opens in, which modes
the strip offers, that only the initial mode is seeded, that a bare mode
switch is never an edit, that each mode keeps its own live draft, and that
Raw is the one editor in the app that gates a commit on JSON syntax rather
than handing raw text straight to the validator. These are exactly the
places silent data loss (an unparseable Raw draft becoming a broken string,
a mode switch silently invalidating an untouched card, a None grid cell
making a value permanently unrepresentable) would hide.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from core import bpx_gateway
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.bodies import ExpressionBody, NumberBody
from ui_qt.cards.function import (
    FLOAT_INT,
    FUNCTION,
    INTERPOLATED_TABLE,
    FunctionCard,
    initial_mode,
    table_is_representable,
)
from ui_qt.cards.modal import RAW_MODE, Mode, ModalCard
from ui_qt.cards.registry import create_card


@pytest.fixture(autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _fn(value, unit="m2.s-1") -> FunctionCard:
    param = ParameterItem(
        label="Diffusivity [m2.s-1]",
        path=("Parameterisation", "Negative electrode", "Diffusivity [m2.s-1]"),
        kind=ParameterKind.FUNCTION,
        value=value,
        unit=unit,
    )
    return create_card(param, None)


# ----------------------------------------------------------------------
# initial_mode: which representation a committed value opens in
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (3.7, FLOAT_INT),
        (5, FLOAT_INT),
        (None, FLOAT_INT),
        ("2*x", FUNCTION),
        ({"x": [0, 1], "y": [1, 2]}, INTERPOLATED_TABLE),
        ({"x": [0, 1], "y": [1]}, RAW_MODE),  # ragged -- no grid form
        ({"x": [0, 1], "y": [1, 2], "z": [9, 9]}, RAW_MODE),  # extra key would be dropped
        ({}, RAW_MODE),
        (True, RAW_MODE),  # legal BPX, but no numeric editor round-trips a bool
        ([1, 2], RAW_MODE),
    ],
)
def test_initial_mode(value, expected):
    assert initial_mode(value) == expected


# ----------------------------------------------------------------------
# table_is_representable: what the two-column x/y grid can hold
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        {"x": [0, 1], "y": [1, 2]},
        {"x": [], "y": []},
        # A None cell is a blank row the grid itself produces (insert_row): it
        # MUST be representable, or the card would turn itself Raw the moment
        # a row was added.
        {"x": [0, None], "y": [1, 2]},
    ],
)
def test_table_representable(value):
    assert table_is_representable(value) is True


@pytest.mark.parametrize(
    "value",
    [
        {"x": [0, 1], "y": [1]},  # ragged
        {"x": [0, 1], "y": [1, 2], "z": [9, 9]},  # extra key
        {},
        "not a dict",
        42,
        {"x": [True], "y": [1]},  # a bool cell would round-trip as the string "True"
    ],
)
def test_table_not_representable(value):
    assert table_is_representable(value) is False


# ----------------------------------------------------------------------
# Strip contents (decision D): decided once, at construction
# ----------------------------------------------------------------------


def test_representable_value_gets_no_raw_mode():
    card = _fn(3.7)
    assert card.mode_labels == (FLOAT_INT, FUNCTION, INTERPOLATED_TABLE)
    assert card._strip is not None  # 3+ modes -> a strip is shown


def test_unrepresentable_value_appends_raw_as_the_last_mode():
    card = _fn({})
    assert card.mode_labels == (FLOAT_INT, FUNCTION, INTERPOLATED_TABLE, RAW_MODE)
    assert card._strip is not None


# ----------------------------------------------------------------------
# Seeding (decision C): only the initial mode is seeded
# ----------------------------------------------------------------------


def test_only_the_initial_mode_is_seeded():
    """Switching mode completely changes the value; the card never invents data
    by carrying a draft across modes."""
    card = _fn(3.7)
    assert card.current_mode == FLOAT_INT
    assert card.value() == 3.7

    card.select_mode(FUNCTION)
    assert card.value() is None  # never seeded, not "3.7"

    card.select_mode(INTERPOLATED_TABLE)
    assert card.value() == {"x": [], "y": []}  # empty grid, not a one-row table

    assert card.is_dirty is False


def test_mode_switch_alone_emits_no_draft_changed():
    """A bare mode switch must never kick the live-validation debounce or mark
    the card touched -- only a real edit should."""
    card = _fn(3.7)
    fired = []
    card.draft_changed.connect(lambda: fired.append(1))

    card.select_mode(FUNCTION)
    card.select_mode(FLOAT_INT)

    assert fired == []
    assert card._touched is False


# ----------------------------------------------------------------------
# Per-mode drafts: each body is built eagerly and kept alive
# ----------------------------------------------------------------------


def test_per_mode_drafts_survive_a_round_trip():
    card = _fn(3.7)
    card.select_mode(FUNCTION)
    card._modes[1].body._edit.setText("2*x")
    assert card.is_dirty is True
    assert card.value() == "2*x"

    card.select_mode(FLOAT_INT)
    assert card.value() == 3.7
    assert card.is_dirty is False  # touched, but the FloatInt draft is unchanged

    card.select_mode(FUNCTION)
    assert card.value() == "2*x"  # the earlier draft is still there


def test_escape_reverts_value_and_mode():
    """Escape must restore every body's draft and return to the initial mode,
    not just the currently visible one."""
    card = _fn(3.7)
    card.select_mode(FUNCTION)
    card._modes[1].body._edit.setText("2*x")

    card._reset_draft()

    assert card.current_mode == FLOAT_INT
    assert card.value() == 3.7
    assert card.is_dirty is False

    card.select_mode(FUNCTION)
    assert card.value() is None  # the "2*x" draft was cleared, not carried over


def test_float_int_to_interpolated_table_commits_a_real_dict():
    card = _fn(3.7)
    card.select_mode(INTERPOLATED_TABLE)
    grid = card._modes[2].body._grid
    grid.insert_row()
    grid._model.setData(grid._model.index(0, 0), "0.1", Qt.EditRole)
    grid._model.setData(grid._model.index(0, 1), "2.5", Qt.EditRole)

    assert card.value() == {"x": [0.1], "y": [2.5]}
    assert card.is_dirty is True


# ----------------------------------------------------------------------
# Raw mode: the one editor that gates a commit on JSON syntax
# ----------------------------------------------------------------------


def test_raw_mode_gates_on_json_syntax():
    seed = {"x": [0, 1], "y": [1]}  # ragged -- opens in Raw
    card = _fn(seed)
    assert card.current_mode == RAW_MODE
    assert card.commit_blocked_reason() is None  # the seeded JSON parses fine

    raw_edit = card._modes[-1].body._edit
    raw_edit.setPlainText('{"x": [0,1], "y": [1]')  # missing closing brace

    reason = card.commit_blocked_reason()
    assert reason is not None
    assert "Not valid JSON" in reason
    # isHidden(), not isVisible(): the window is never shown in this suite, so
    # isVisible() would be False regardless of the widget's own hidden flag.
    assert not card._modes[-1].body._error.isHidden()

    # Unparseable text must NEVER become a broken string -- it falls back to
    # the seed rather than silently destroying the stored table.
    assert card.value() == seed

    raw_edit.setPlainText('{"x": [0,1], "y": [1,2]}')
    assert card.commit_blocked_reason() is None
    assert card._modes[-1].body._error.isHidden()
    assert card.value() == {"x": [0, 1], "y": [1, 2]}

    raw_edit.setPlainText("")
    assert card.commit_blocked_reason() is None  # empty means null, a real value
    assert card.value() is None


def test_raw_mode_accepts_multiline_input_only_while_active():
    card = _fn(True)  # bool -- opens in Raw
    assert card.current_mode == RAW_MODE
    assert card.accepts_multiline_input is True

    card.select_mode(FLOAT_INT)
    assert card.accepts_multiline_input is False


def test_every_mode_stays_clickable_even_when_unrepresentable():
    """Clicking another mode over unrepresentable JSON must not destroy
    anything -- it just shows an empty editor until the user commits."""
    card = _fn({})  # unrepresentable -- opens in Raw
    assert card.current_mode == RAW_MODE

    card.select_mode(FLOAT_INT)
    assert card.value() is None  # empty numeric editor, nothing destroyed


# ----------------------------------------------------------------------
# ExpressionBody: lenient like every other free-text editor
# ----------------------------------------------------------------------


def test_expression_body_parses_a_bare_number_as_a_number():
    """A bare numeric expression commits as a float, not the string "3.7", so
    the value reclassifies into FloatInt mode on the next rebuild."""
    body = ExpressionBody()
    body._edit.setText("3.7")
    assert body.value() == 3.7
    assert type(body.value()) is float


def test_expression_body_passes_through_a_real_expression():
    body = ExpressionBody()
    body._edit.setText("2*x")
    assert body.value() == "2*x"


def test_function_hint_quotes_bpx_function_docstring():
    card = _fn(3.7)
    help_text = bpx_gateway.function_syntax_help()
    labels = card._modes[1].body.findChildren(QLabel)
    assert any(label.text() == help_text for label in labels)


# ----------------------------------------------------------------------
# ModalCard: a single-representation kind shows no strip (decision D)
# ----------------------------------------------------------------------


def test_modal_card_with_a_single_mode_shows_no_strip():
    param = ParameterItem(
        label="Solo",
        path=("Parameterisation", "Cell", "Solo"),
        kind=ParameterKind.FUNCTION,
        value=5.0,
    )
    card = ModalCard(param, None, [Mode("Only", NumberBody(""))], 0)
    assert card._strip is None
    assert card.mode_labels == ("Only",)
