"""Card registry contract: every editable parameter kind gets an editable card.

The important behaviour is that no editable kind ever falls back to a read-only
card (which would trap the user with a visible-but-uneditable value). We assert
the ``is_editable`` contract rather than concrete card classes, so the registry
can be reorganised without breaking these tests.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QSpinBox

from core.bpx_gateway import FieldMeta
from core.parameter_types import ParameterKind, classify
from core.tree_model import ParameterItem
from core.values import values_equal
from ui_qt.cards.registry import create_card


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "kind, value",
    [
        (ParameterKind.SCALAR, 1.0),
        (ParameterKind.INTEGER, 3),
        (ParameterKind.ENUM, "SPM"),
        (ParameterKind.FUNCTION, "not-a-function"),
        (ParameterKind.UNKNOWN, None),
        # TABLE gets a real editor now: a rectangular x/y table (TableCard) or,
        # for a value the grid cannot show, an editable Raw fallback -- never a
        # read-only view.
        (ParameterKind.TABLE, {"x": [0, 1], "y": [2, 3]}),
        (ParameterKind.TABLE, {"x": [0, 1], "y": [2]}),  # ragged -> Raw fallback
        (ParameterKind.TABLE, {}),
    ],
)
def test_editable_kinds_produce_editable_cards(kind, value):
    """Editable kinds never fall back to a read-only card, even for an invalid
    stored value -- otherwise the user could not repair it."""
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=kind, value=value)
    card = create_card(param, None)
    assert card.is_editable


def test_section_kind_falls_back_to_read_only():
    """A SECTION is a container, not a value: it has no editor and stays
    read-only. (TABLE used to sit here too; it now has a real editor.)"""
    _app()
    param = ParameterItem(
        label="T", path=("Header", "T"), kind=ParameterKind.SECTION, value={}
    )
    card = create_card(param, None)
    assert card.is_editable is False


def test_unknown_kind_produces_editable_raw_card():
    """A no-metadata, value-less custom parameter (``UNKNOWN``) gets the
    editable raw fallback card rather than the read-only dead end."""
    _app()
    param = ParameterItem(
        label="Custom", path=("Header", "Custom"), kind=ParameterKind.UNKNOWN, value=None
    )
    card = create_card(param, None)
    assert card.is_editable
    assert type(card).__name__ == "RawCard"
    assert card._edit.text() == ""
    assert card.value() is None  # empty free text is honest "no value", not ""


def test_unknown_kind_raw_card_commits_and_reverts():
    """Typing into the raw card commits via the normal ``value()``/``reset()``
    contract, and Escape-equivalent ``reset()`` restores the original."""
    _app()
    param = ParameterItem(
        label="Custom", path=("Header", "Custom"), kind=ParameterKind.UNKNOWN, value=None
    )
    card = create_card(param, None)
    card._edit.setText("5")
    assert card.value() == 5
    card.reset()
    assert card._edit.text() == ""
    assert card.value() is None


def _input_widget(card):
    """The card's active input widget, whatever layout the card uses.

    A ``ModalCard`` (FunctionCard) has no single input: it delegates to
    whichever mode body is showing, so ask it.
    """
    focus_widget = getattr(card, "focus_widget", None)
    if callable(focus_widget):
        return focus_widget()
    for attr in ("_edit", "_fallback", "_spin", "_combo"):
        widget = getattr(card, attr, None)
        if widget is not None:
            return widget
    raise AssertionError(f"unrecognised card widget layout: {card!r}")


def _rendered_text(card) -> str:
    """Return the visible text of whichever input widget the card is using.

    Only single-line inputs have a rendered "text". A ModalCard in its Raw or
    InterpolatedTable mode exposes a QPlainTextEdit or QTableView instead; fail
    loudly there rather than let a future caller silently reach for ``.text()``.
    """
    widget = _input_widget(card)
    if isinstance(widget, QSpinBox):
        return str(widget.value())
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, QLineEdit):
        return widget.text()
    raise AssertionError(
        f"{type(widget).__name__} has no single-line text; assert on card.value() instead."
    )


@pytest.mark.parametrize(
    "kind",
    [
        ParameterKind.SCALAR,
        ParameterKind.INTEGER,
        ParameterKind.ENUM,
        ParameterKind.FUNCTION,
        ParameterKind.UNKNOWN,
    ],
)
def test_none_value_renders_empty_without_crashing(kind):
    """A known-alias parameter added with an honest empty value (``None``)
    still opens its proper per-kind editor (metadata is authoritative), and
    that editor must render a blank field -- never the literal string "None"
    and never a fabricated default. The empty draft round-trips back to
    ``None`` -- honest "no value" -- rather than the empty string."""
    _app()
    meta = (
        FieldMeta(alias="P", is_enum=True, enum_values=("SPM", "SPMe"))
        if kind is ParameterKind.ENUM
        else None
    )
    param = ParameterItem(label="P", path=("Header", "P"), kind=kind, value=None)
    card = create_card(param, meta)
    assert card.is_editable
    assert _rendered_text(card) == ""
    assert card.value() is None


def test_enum_none_value_has_no_selection():
    """The combo must not silently default to its first entry; ``None`` is a
    genuine no-selection state, not "the first enum value"."""
    _app()
    meta = FieldMeta(alias="P", is_enum=True, enum_values=("SPM", "SPMe"))
    param = ParameterItem(
        label="P", path=("Header", "P"), kind=ParameterKind.ENUM, value=None
    )
    card = create_card(param, meta)
    assert card._combo.currentIndex() == -1


def test_enum_none_value_can_be_selected_and_reverted():
    _app()
    meta = FieldMeta(alias="P", is_enum=True, enum_values=("SPM", "SPMe"))
    param = ParameterItem(
        label="P", path=("Header", "P"), kind=ParameterKind.ENUM, value=None
    )
    card = create_card(param, meta)
    card._combo.setCurrentIndex(1)
    assert card.value() == "SPMe"
    card.reset()
    assert card._combo.currentIndex() == -1
    assert card.value() is None


def _model_enum_card():
    meta = FieldMeta(alias="Model", is_enum=True, enum_values=("SPM", "SPMe", "DFN"))
    param = ParameterItem(
        label="Model", path=("Header", "Model"), kind=ParameterKind.ENUM, value="SPM"
    )
    return create_card(param, meta)


def test_enum_popup_pick_commits_immediately():
    """Opening the dropdown and choosing an entry is a complete act: it must
    commit without a further Enter (this is how the document's Model is
    switched -- a pick that silently stays a draft looks like it didn't take).
    The draft fires before the commit, so the commit sees the new value."""
    _app()
    card = _model_enum_card()
    order = []
    card.draft_changed.connect(lambda: order.append("draft"))
    card.commit_requested.connect(lambda: order.append("commit"))

    card._combo.showPopup()  # the user opened the menu...
    index = card._combo.findText("DFN")
    card._combo.setCurrentIndex(index)
    card._combo.activated.emit(index)  # ...and picked an entry

    assert order == ["draft", "commit"]
    assert card.value() == "DFN"


def test_enum_closed_combo_arrowing_stays_a_draft():
    """Stepping through values on the *closed* combo is browsing, not
    choosing: it must not commit each step (Enter still commits, Escape still
    reverts, and every step would otherwise become an undo entry)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    _app()
    card = _model_enum_card()
    commits = []
    card.commit_requested.connect(lambda: commits.append(True))

    QTest.keyClick(card._combo, Qt.Key_Down)  # SPM -> SPMe, popup never opened

    assert card.value() == "SPMe"
    assert commits == []  # a draft; Enter is what commits it


@pytest.mark.parametrize(
    "kind, text, expected_value",
    [
        (ParameterKind.SCALAR, "3.5", 3.5),
        (ParameterKind.FUNCTION, "x + 1", "x + 1"),
        (ParameterKind.UNKNOWN, "x + 1", "x + 1"),
    ],
)
def test_none_value_can_be_typed_and_reverted(kind, text, expected_value):
    """Typing into a freshly-empty scalar/function field commits through the
    normal ``value()``/``reset()`` contract, unchanged by the ``None`` origin."""
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=kind, value=None)
    card = create_card(param, None)
    _input_widget(card).setText(text)
    assert card.value() == expected_value
    card.reset()
    assert _rendered_text(card) == ""
    assert card.value() is None


def test_known_alias_with_none_value_opens_proper_editor_end_to_end():
    """The exact F3 scenario: a known-alias parameter added with an honest
    empty value (``value=None``, e.g. via the ``AddParameter`` command) is
    metadata-authoritative in ``classify`` and must open the real per-kind
    editor -- never the raw/unknown fallback -- rendering it empty."""
    _app()
    meta = FieldMeta(alias="Chemistry", is_enum=True, enum_values=("SPM", "SPMe"))
    kind = classify(None, meta)
    assert kind is ParameterKind.ENUM
    param = ParameterItem(
        label="Chemistry", path=("Header", "Chemistry"), kind=kind, value=None
    )
    card = create_card(param, meta)
    assert card.is_editable
    assert card._combo.currentIndex() == -1


# ---------------------------------------------------------------------------
# Registry routing for the declared TEXT/BOOLEAN/SERIES kinds, the interim card
# shim for the still-unbuilt MAP kind, and the FUNCTION/MAP value-dependent
# dispatch -- see docs/architecture.md "Editing Architecture". These lock today's
# behaviour so a later real card (Phase 4c/5) is a deliberate, visible change
# rather than a silent one.
# ---------------------------------------------------------------------------


def test_text_kind_uses_text_card():
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=ParameterKind.TEXT, value="hello")
    card = create_card(param, None)
    assert type(card).__name__ == "TextCard"
    assert card.is_editable


def test_boolean_kind_uses_boolean_card():
    _app()
    param = ParameterItem(
        label="P", path=("Header", "P"), kind=ParameterKind.BOOLEAN, value=True
    )
    card = create_card(param, None)
    assert type(card).__name__ == "BooleanCard"
    assert card.is_editable


def test_series_kind_uses_series_card():
    """SERIES now has a real grid editor (Phase 4b); see test_series_card.py
    for its behaviour and for the unrepresentable-value fallback."""
    _app()
    param = ParameterItem(
        label="P", path=("Validation", "run", "Time [s]"), kind=ParameterKind.SERIES, value=[0, 1]
    )
    card = create_card(param, None)
    assert type(card).__name__ == "SeriesCard"
    assert card.is_editable


def test_function_kind_with_dict_value_opens_the_table_mode():
    """A table-valued FUNCTION field is a first-class representation now: the
    mode strip opens on InterpolatedTable rather than trapping it read-only.
    See test_modal_cards.py for the strip's full behaviour."""
    _app()
    param = ParameterItem(
        label="OCP [V]",
        path=("Parameterisation", "Negative electrode", "OCP [V]"),
        kind=ParameterKind.FUNCTION,
        value={"x": [0, 1], "y": [2, 3]},
    )
    card = create_card(param, None)
    assert type(card).__name__ == "FunctionCard"
    assert card.current_mode == "InterpolatedTable"
    assert card.is_editable


def test_function_kind_with_numeric_value_uses_function_card_with_unit():
    """A numeric constant in a FUNCTION field opens FunctionCard's FloatInt
    mode (not ScalarCard, per the removed value-shape exception), showing the
    unit label exactly as ScalarCard does."""
    _app()
    param = ParameterItem(
        label="Diffusivity [m2.s-1]",
        path=("Parameterisation", "Negative electrode", "Diffusivity [m2.s-1]"),
        kind=ParameterKind.FUNCTION,
        value=3.3e-14,
        unit="m2.s-1",
    )
    card = create_card(param, None)
    assert type(card).__name__ == "FunctionCard"
    assert card.current_mode == "FloatInt"
    assert _rendered_text(card) == str(3.3e-14)


@pytest.mark.parametrize(
    "value",
    [1.0, 5, None, {"Primary": 1.0, "Secondary": 5.0}, [1, 2], True],
)
def test_map_kind_always_gets_an_editable_map_card(value):
    """Every MAP value -- scalar, None, per-material dict, or an invalid shape
    -- gets the editable MapCard, never a read-only view. The card decides its
    own opening mode (FloatInt / dict / Raw); the registry never falls back."""
    _app()
    param = ParameterItem(
        label="LAM: Positive electrode",
        path=("State", "Degradation", "LAM: Positive electrode"),
        kind=ParameterKind.MAP,
        value=value,
    )
    card = create_card(param, None)
    assert type(card).__name__ == "MapCard"
    assert card.is_editable is True


def test_integer_none_value_uses_fallback_and_can_be_typed():
    """A ``None`` original is not a valid int, so the integer card falls back
    to its free-text widget (the existing invalid-original path) rather than
    crashing a ``QSpinBox`` on ``int(None)``."""
    _app()
    param = ParameterItem(
        label="P", path=("Header", "P"), kind=ParameterKind.INTEGER, value=None
    )
    card = create_card(param, None)
    assert card._spin is None
    assert card._fallback.text() == ""
    assert card.value() is None
    card._fallback.setText("5")
    assert card.value() == 5
    card.reset()
    assert card._fallback.text() == ""
    assert card.value() is None


# ---------------------------------------------------------------------------
# is_dirty: type-aware dirty-checking (docs/architecture.md "Editing
# Architecture" -- commit only when the draft differs).
# ---------------------------------------------------------------------------


def test_is_dirty_false_for_an_unchanged_scalar_draft():
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=ParameterKind.SCALAR, value=5.0)
    card = create_card(param, None)
    assert card.is_dirty is False


def test_is_dirty_true_for_float_typed_over_an_int_original():
    """``5 == 5.0`` in Python, but they are different JSON values -- typing
    "5.0" over a stored ``5`` must count as a real edit."""
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=ParameterKind.SCALAR, value=5)
    card = create_card(param, None)
    card._edit.setText("5.0")
    assert card.value() == 5.0
    assert card.is_dirty is True


def test_values_equal_distinguishes_json_types():
    """``5 == 5.0`` and ``True == 1`` in Python, but each pair has a different
    JSON representation, so the dirty-check's equality must separate them."""
    assert values_equal(5.0, 5.0) is True
    assert values_equal(5, 5.0) is False
    assert values_equal(True, 1) is False
    assert values_equal(None, "") is False


def test_untouched_card_is_never_dirty_even_when_it_cannot_render_the_original():
    """A card whose widget cannot faithfully hold the stored value still must
    not report an edit the user never made.

    Here a BooleanCard is handed the int ``1`` (unreachable via ``classify``,
    which tests ``bool`` before ``int``, but the invariant must hold anyway):
    the checkbox can only read back a real ``bool``, so a pure value
    comparison would call it dirty and a bare Enter would rewrite ``1`` to
    ``true``. This is the same failure mode as a stored ``null`` in a
    TextCard.
    """
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=ParameterKind.BOOLEAN, value=1)
    card = create_card(param, None)
    assert card.value() is True  # BooleanCard always yields a real bool
    assert card.is_dirty is False  # ... but nothing was touched, so nothing commits


def test_toggling_a_boolean_over_an_equal_int_original_is_dirty():
    """Once the user *does* interact, ``True`` over a stored ``1`` is a real
    kind-changing edit, even though ``True == 1``."""
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=ParameterKind.BOOLEAN, value=1)
    card = create_card(param, None)
    card._check.toggle()  # -> False
    card._check.toggle()  # -> back to True, but now touched
    assert card.value() is True
    assert card.is_dirty is True


def test_is_dirty_false_for_an_unchanged_boolean_draft():
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=ParameterKind.BOOLEAN, value=True)
    card = create_card(param, None)
    assert card.is_dirty is False


def test_is_dirty_false_for_an_unchanged_text_draft():
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=ParameterKind.TEXT, value="hello")
    card = create_card(param, None)
    assert card.is_dirty is False


def test_is_dirty_true_for_edited_text_draft():
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=ParameterKind.TEXT, value="hello")
    card = create_card(param, None)
    card._edit.setPlainText("hello world")
    assert card.is_dirty is True
