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

from PySide6.QtWidgets import QApplication

from core.bpx_gateway import FieldMeta
from core.parameter_types import ParameterKind, classify
from core.tree_model import ParameterItem
from ui_qt.cards.base import _values_equal
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
    ],
)
def test_editable_kinds_produce_editable_cards(kind, value):
    """Editable kinds never fall back to a read-only card, even for an invalid
    stored value -- otherwise the user could not repair it."""
    _app()
    param = ParameterItem(label="P", path=("Header", "P"), kind=kind, value=value)
    card = create_card(param, None)
    assert card.is_editable


@pytest.mark.parametrize("kind", [ParameterKind.TABLE, ParameterKind.SECTION])
def test_structural_kinds_fall_back_to_read_only(kind):
    """Structural kinds (tables/sections) have no editor and stay read-only.

    ``UNKNOWN`` is deliberately excluded here: B1 gives it a real editable
    raw fallback card (see ``test_unknown_kind_produces_editable_raw_card``).
    """
    _app()
    param = ParameterItem(label="T", path=("Header", "T"), kind=kind, value={})
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


def _rendered_text(card) -> str:
    """Return the visible text of whichever input widget the card is using."""
    edit = getattr(card, "_edit", None)
    if edit is not None:
        return edit.text()
    fallback = getattr(card, "_fallback", None)
    if fallback is not None:
        return fallback.text()
    spin = getattr(card, "_spin", None)
    if spin is not None:
        return str(spin.value())
    combo = getattr(card, "_combo", None)
    if combo is not None:
        return combo.currentText()
    raise AssertionError(f"unrecognised card widget layout: {card!r}")


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
    card._edit.setText(text)
    assert card.value() == expected_value
    card.reset()
    assert card._edit.text() == ""
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
# Registry routing for the declared TEXT/BOOLEAN kinds, and interim card
# shims for the still-unbuilt kinds (SERIES, MAP) and the FUNCTION/MAP
# value-dependent dispatch -- see docs/03-features.md §4 "Input system".
# These lock today's stand-in behaviour so a later real card (Phase 4/5) is
# a deliberate, visible change rather than a silent one.
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


def test_series_kind_falls_back_to_read_only():
    """SERIES has no editor yet; it stays read-only (Phase 4 covers series
    grids)."""
    _app()
    param = ParameterItem(
        label="P", path=("Validation", "run", "Time [s]"), kind=ParameterKind.SERIES, value=[0, 1]
    )
    card = create_card(param, None)
    assert type(card).__name__ == "ReadOnlyCard"
    assert card.is_editable is False


def test_function_kind_with_dict_value_falls_back_to_read_only():
    """A table-valued FUNCTION field must not reach the free-text
    FunctionCard: str(dict) is Python repr and committing it would corrupt
    the value."""
    _app()
    param = ParameterItem(
        label="OCP [V]",
        path=("Parameterisation", "Negative electrode", "OCP [V]"),
        kind=ParameterKind.FUNCTION,
        value={"x": [0, 1], "y": [2, 3]},
    )
    card = create_card(param, None)
    assert type(card).__name__ == "ReadOnlyCard"


def test_function_kind_with_numeric_value_uses_function_card_with_unit():
    """A numeric constant in a FUNCTION field now opens FunctionCard (not
    ScalarCard, per the removed value-shape exception), and FunctionCard
    shows the unit label exactly as ScalarCard does."""
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
    assert card._edit.text() == str(3.3e-14)


@pytest.mark.parametrize(
    "value, expected_card",
    [
        (1.0, "ScalarCard"),
        (5, "ScalarCard"),
        (None, "RawCard"),
        ({"Primary": 1.0, "Secondary": 5.0}, "ReadOnlyCard"),
    ],
)
def test_map_kind_dispatches_by_stored_value_shape(value, expected_card):
    """MAP's interim dispatch: numeric (non-bool) -> ScalarCard, None ->
    RawCard, dict -> ReadOnlyCard (real MapCard is Phase 4)."""
    _app()
    param = ParameterItem(
        label="LAM: Positive electrode",
        path=("State", "Degradation", "LAM: Positive electrode"),
        kind=ParameterKind.MAP,
        value=value,
    )
    card = create_card(param, None)
    assert type(card).__name__ == expected_card


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
# is_dirty: type-aware dirty-checking (docs/03-features.md §4 "commit only
# when the draft differs").
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
    assert _values_equal(5.0, 5.0) is True
    assert _values_equal(5, 5.0) is False
    assert _values_equal(True, 1) is False
    assert _values_equal(None, "") is False


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
