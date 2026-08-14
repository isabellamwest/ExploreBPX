"""ModalCard + mode bodies: the mode-switching editor for union-typed BPX
fields.

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
from core.csv_import import read_csv_text
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.bodies import ExpressionBody, MaterialMapBody, NumberBody
from ui_qt.cards.function import (
    FLOAT_INT,
    FUNCTION,
    INTERPOLATED_TABLE,
    FunctionCard,
    initial_mode,
    table_is_representable,
)
from ui_qt.cards.map import (
    DICT_STR_FLOAT_INT,
    MapCard,
    map_is_representable,
)
from ui_qt.cards.map import initial_mode as map_initial_mode
from ui_qt.cards.modal import RAW_MODE, ModalCard, Mode, RawValueCard
from ui_qt.cards.multi_series_chart import charts_available
from ui_qt.cards.paste_dialog import PastePreviewResult
from ui_qt.cards.registry import create_card
from ui_qt.cards.table import TableCard


@pytest.fixture(autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


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
    ("value", "expected"),
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
# Strip contents: decided once, at construction
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
# Seeding: only the initial mode is seeded
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
# CSV import into TableBody: a draft like a paste, not a command -- this
# body writes only the parameter it belongs to, unlike SeriesCard's import,
# which fills sibling parameters and therefore must go through a command.
# ----------------------------------------------------------------------


def test_function_card_table_mode_has_a_csv_import_button_always_visible():
    """The entry point itself, not just the write path the tests above reach
    past: ``InterpolatedTable``'s grid must actually opt into ``csv_import``,
    and the button must stay visible whatever height the grid has grown to."""
    card = _fn(3.7)
    card.select_mode(INTERPOLATED_TABLE)
    grid = card._modes[2].body._grid
    assert grid._import_button is not None
    assert not grid._import_button.isHidden()
    grid.set_fill_available(True)
    assert not grid._import_button.isHidden()
    grid.set_fill_available(False)
    assert not grid._import_button.isHidden()


def test_function_card_csv_import_into_table_mode_is_dirty_and_commits_a_real_dict():
    card = _fn(3.7)
    card.select_mode(INTERPOLATED_TABLE)
    grid = card._modes[2].body._grid

    data = read_csv_text("x,y\n0.1,2.5\n0.2,3.0\n")
    grid._apply_csv_mapping(data, (0, 1), PastePreviewResult.REPLACE)

    assert card.is_dirty is True
    assert card.value() == {"x": [0.1, 0.2], "y": [2.5, 3.0]}


def test_function_card_escape_discards_a_table_csv_import():
    card = _fn(3.7)
    card.select_mode(INTERPOLATED_TABLE)
    grid = card._modes[2].body._grid

    data = read_csv_text("x,y\n0.1,2.5\n")
    grid._apply_csv_mapping(data, (0, 1), PastePreviewResult.REPLACE)
    assert card.is_dirty is True

    card._reset_draft()

    assert card.current_mode == FLOAT_INT  # mode reverts too
    assert card.value() == 3.7
    assert card.is_dirty is False


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
    """The hint stays bpx's own words, only mechanically collapsed onto one
    line -- the same transform ExpressionBody applies."""
    card = _fn(3.7)
    lines = bpx_gateway.function_syntax_help().splitlines()
    expected = " · ".join(line.strip().lstrip("- ") for line in lines if line.strip())
    labels = card._modes[1].body.findChildren(QLabel)
    assert any(label.text() == expected for label in labels)


# ----------------------------------------------------------------------
# ExpressionBody: the committed-value chart preview
# ----------------------------------------------------------------------

requires_charts = pytest.mark.skipif(not charts_available(), reason="QtCharts not available in this PySide6 build")


@requires_charts
def test_expression_chart_samples_the_committed_expression():
    card = _fn("2*x", unit="V")
    body = card._expression_body
    name, _colour, points = body._chart._series_meta["main"]
    assert name == "Main"
    assert len(points) == 200
    assert points[0][0] == pytest.approx(0.0)  # default domain [0, 1]
    assert points[-1][0] == pytest.approx(1.0)


@requires_charts
def test_expression_chart_y_axis_names_the_unit():
    card = _fn("2*x", unit="V")
    assert card._expression_body._chart._axis_y.titleText() == "y [V]"


@requires_charts
def test_expression_chart_y_axis_falls_back_to_bare_y_without_a_unit():
    card = _fn("2*x", unit="")
    assert card._expression_body._chart._axis_y.titleText() == "y"


@requires_charts
def test_expression_chart_domain_edit_resamples_the_curve():
    card = _fn("2*x", unit="V")
    body = card._expression_body

    body._domain_high_edit.setText("2")
    body._domain_high_edit.editingFinished.emit()

    xs = [x for x, _y in body._chart._series_meta["main"][2]]
    assert max(xs) == pytest.approx(2.0)


@requires_charts
def test_expression_chart_invalid_domain_text_reverts_both_fields():
    card = _fn("2*x", unit="V")
    body = card._expression_body

    body._domain_high_edit.setText("not a number")
    body._domain_high_edit.editingFinished.emit()

    assert body._domain_low_edit.text() == "0"
    assert body._domain_high_edit.text() == "1"


@requires_charts
def test_expression_chart_low_greater_than_high_reverts():
    card = _fn("2*x", unit="V")
    body = card._expression_body

    body._domain_low_edit.setText("5")
    body._domain_low_edit.editingFinished.emit()

    assert body._domain_low_edit.text() == "0"  # low >= high: rejected whole


@requires_charts
def test_expression_chart_invalid_function_shows_a_muted_note_and_no_chart():
    card = _fn("2x")  # missing '*': not a legal bpx.Function
    body = card._expression_body

    assert not body._error_note.isHidden()
    assert body._error_note.text().startswith("Invalid Function")
    assert body._chart.isHidden()


@requires_charts
def test_expression_chart_valid_resample_replaces_the_note():
    """A commit rebuilds the card from the fresh value (``show_parameter``),
    which reseeds the body through ``set_value`` -- the same hook a fresh,
    now-valid expression repopulates through."""
    card = _fn("2x")
    body = card._expression_body
    assert not body._error_note.isHidden()

    body.set_value("2*x")

    assert body._error_note.isHidden()
    assert not body._chart.isHidden()


# ----------------------------------------------------------------------
# ModalCard: a single-representation kind shows no strip
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


# ======================================================================
# MapCard: FloatInt | dict[str, FloatInt] (+ conditional Raw)
# ======================================================================


def _map(value, suggestions=()) -> MapCard:
    param = ParameterItem(
        label="LAM: Positive electrode",
        path=("State", "Degradation", "LAM: Positive electrode"),
        kind=ParameterKind.MAP,
        value=value,
        key_suggestions=suggestions,
    )
    return create_card(param, None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.0, FLOAT_INT),
        (5, FLOAT_INT),
        (None, FLOAT_INT),
        ({"Primary": 1.0, "Secondary": 2.0}, DICT_STR_FLOAT_INT),
        ({"Primary": 1.0}, DICT_STR_FLOAT_INT),
        (True, RAW_MODE),  # bool: no numeric editor round-trips it
        ([1, 2], RAW_MODE),
        ({"Primary": [1, 2]}, RAW_MODE),  # a list value has no cell to sit in
    ],
)
def test_map_initial_mode(value, expected):
    assert map_initial_mode(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        {"Primary": 1.0, "Secondary": 2.0},
        {"Primary": 1},
        {},
        {"Primary": None},  # a None cell is a blank row the grid produces
    ],
)
def test_map_representable(value):
    assert map_is_representable(value) is True


@pytest.mark.parametrize(
    "value",
    [
        {"Primary": [1, 2]},  # nested list -- no cell form
        {"Primary": {"a": 1}},  # nested dict
        {"Primary": True},  # bool cell would round-trip as "True"
        [1, 2],
        42,
    ],
)
def test_map_not_representable(value):
    assert map_is_representable(value) is False


def test_map_representable_dict_gets_no_raw_mode():
    card = _map({"Primary": 1.0}, ("Primary", "Secondary"))
    assert card.mode_labels == (FLOAT_INT, DICT_STR_FLOAT_INT)
    assert card.current_mode == DICT_STR_FLOAT_INT


def test_map_unrepresentable_value_appends_raw():
    card = _map([1, 2])
    assert card.mode_labels == (FLOAT_INT, DICT_STR_FLOAT_INT, RAW_MODE)
    assert card.current_mode == RAW_MODE


def test_map_scalar_opens_in_float_int():
    card = _map(1.0)
    assert card.current_mode == FLOAT_INT
    assert card.value() == 1.0


def test_map_dict_round_trips_its_value():
    card = _map({"Primary": 1.0, "Secondary": 2.0}, ("Primary", "Secondary"))
    assert card.value() == {"Primary": 1.0, "Secondary": 2.0}
    assert card.is_dirty is False


def test_map_mode_switch_alone_is_not_an_edit():
    card = _map(3.7, ("Primary",))
    fired = []
    card.draft_changed.connect(lambda: fired.append(1))
    card.select_mode(DICT_STR_FLOAT_INT)
    assert fired == []
    assert card._touched is False
    assert card.is_dirty is False
    assert card.value() == {}  # empty dict body, never seeded from 3.7


def test_map_float_int_to_dict_commits_a_real_dict():
    card = _map(3.7, ("Primary",))
    card.select_mode(DICT_STR_FLOAT_INT)
    body = card._modes[1].body
    body._add_material("Primary")
    grid = body._grid
    grid._model.setData(grid._model.index(0, 1), "0.5", Qt.EditRole)
    assert card.value() == {"Primary": 0.5}
    assert card.is_dirty is True


def test_map_escape_reverts_value_and_mode():
    card = _map(3.7, ("Primary",))
    card.select_mode(DICT_STR_FLOAT_INT)
    card._modes[1].body._add_material("Primary")
    card._reset_draft()
    assert card.current_mode == FLOAT_INT
    assert card.value() == 3.7
    assert card.is_dirty is False


# ----------------------------------------------------------------------
# MaterialMapBody: keys verbatim, duplicates blocked, suggestions offered
# ----------------------------------------------------------------------


def test_material_map_body_builds_a_dict_from_rows():
    body = MaterialMapBody(("Primary", "Secondary"))
    body.set_value({"Primary": 1.0, "Secondary": 2.0})
    assert body.value() == {"Primary": 1.0, "Secondary": 2.0}
    assert body.commit_blocked_reason() is None


def test_material_map_body_keeps_a_numeric_key_as_text():
    """The key column is verbatim text (a material name), so a key that looks
    like a number is never coerced into one."""
    body = MaterialMapBody(())
    body._grid.append_row(["1", 5.0])
    assert body.value() == {"1": 5.0}
    assert list(body.value().keys()) == ["1"]


def test_material_map_body_blocks_a_duplicate_key():
    body = MaterialMapBody(())
    body.set_value({"Primary": 1.0})
    body._grid.append_row(["Primary", 9.0])
    reason = body.commit_blocked_reason()
    assert reason is not None
    assert "Duplicate material" in reason
    assert "Primary" in reason
    assert not body._error.isHidden()


def test_material_map_body_skips_an_unkeyed_row():
    """A value typed before its material name is not yet a dict entry -- it is
    skipped rather than inventing a "" key for it."""
    body = MaterialMapBody(())
    body._grid.append_row([None, 5.0])
    assert body.value() == {}
    assert body.commit_blocked_reason() is None


def test_material_map_body_offers_only_unused_suggestions():
    body = MaterialMapBody(("Primary", "Secondary"))
    body.set_value({"Primary": 1.0})
    body._populate_menu()
    labels = [a.text() for a in body._menu.actions()]
    assert labels == ["Secondary"]  # Primary is already used


def test_material_map_body_with_no_suggestions_has_no_menu_button():
    """A single-particle electrode: the dict mode is still reachable (decision
    F), but there are no names to suggest, so only the plain + row remains."""
    body = MaterialMapBody(())
    assert not hasattr(body, "_menu")


# ======================================================================
# TableCard: a User-defined x/y table, no strip; Raw fallback for ragged
# ======================================================================


def _table(value) -> TableCard:
    param = ParameterItem(
        label="My table",
        path=("Parameterisation", "User-defined", "My table"),
        kind=ParameterKind.TABLE,
        value=value,
    )
    return create_card(param, None)


def test_table_card_has_no_strip_and_round_trips():
    card = _table({"x": [0, 1, 2], "y": [3, 4, 5]})
    assert isinstance(card, TableCard)
    assert card._strip is None  # one representation, no mode strip
    assert card.value() == {"x": [0, 1, 2], "y": [3, 4, 5]}
    assert card.is_dirty is False


def test_table_ragged_value_falls_back_to_raw():
    card = _table({"x": [0, 1], "y": [1]})
    assert isinstance(card, RawValueCard)
    assert card.is_editable is True
    assert card._strip is None


def test_table_card_has_a_csv_import_button_always_visible():
    """The entry point itself, not just the write path the test below reaches
    past: the grid must actually opt into ``csv_import``, and the button must
    stay visible whatever height the grid has grown to."""
    card = _table({"x": [0, 1], "y": [1, 2]})
    grid = card._modes[0].body._grid
    assert grid._import_button is not None
    assert not grid._import_button.isHidden()
    grid.set_fill_available(True)
    assert not grid._import_button.isHidden()
    grid.set_fill_available(False)
    assert not grid._import_button.isHidden()


def test_table_card_csv_import_is_dirty_and_escape_restores_the_original():
    card = _table({"x": [0, 1], "y": [1, 2]})
    grid = card._modes[0].body._grid

    data = read_csv_text("x,y\n5,6\n7,8\n")
    grid._apply_csv_mapping(data, (0, 1), PastePreviewResult.REPLACE)

    assert card.is_dirty is True
    assert card.value() == {"x": [5, 7], "y": [6, 8]}

    card._reset_draft()

    assert card.value() == {"x": [0, 1], "y": [1, 2]}
    assert card.is_dirty is False


# ======================================================================
# RawValueCard: the JSON fallback for single-representation kinds
# ======================================================================


def test_raw_value_card_gates_on_json_and_stays_editable():
    param = ParameterItem(
        label="badseries",
        path=("Validation", "run", "Time [s]"),
        kind=ParameterKind.SERIES,
        value={"oops": 1},  # not a list -- unrepresentable series
    )
    card = create_card(param, None)
    assert isinstance(card, RawValueCard)
    assert card._strip is None
    assert card.is_editable is True
    assert card.value() == {"oops": 1}

    edit = card._modes[0].body._edit
    edit.setPlainText("{not json")
    assert card.commit_blocked_reason() is not None
    assert card.value() == {"oops": 1}  # falls back to seed, never a broken string


def test_a_long_expression_reads_from_its_start(qtbot):
    """A QLineEdit scrolls to the cursor, and setText leaves it at the end,
    so a long OCP expression showed only its tail. The modeller must be able
    to see what their own function begins with."""
    from ui_qt.cards.bodies import ExpressionBody

    body = ExpressionBody()
    qtbot.addWidget(body)
    body.set_value("9.47e-01 * exp(-x) + 5.42e+04 * tanh(-3.19 * (x - 2.01))")

    assert body._edit.cursorPosition() == 0

    body._edit.setCursorPosition(20)
    body.reset()
    assert body._edit.cursorPosition() == 0


def test_the_expression_hint_is_never_given_less_height_than_it_needs(qtbot):
    """Wrapped help text lost its second line inside the mode strip's
    stacked layout, which does not carry a label's height-for-width."""
    from ui_qt.cards.hint import WrappedHelp

    help_text = WrappedHelp("word " * 60)
    qtbot.addWidget(help_text)
    help_text.resize(200, 10)
    help_text.show()
    qtbot.waitExposed(help_text)

    assert help_text.minimumHeight() >= help_text.heightForWidth(help_text.width())
