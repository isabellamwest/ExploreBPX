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
    assert card.value() == ""


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
    assert card.value() == ""


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
    and never a fabricated default."""
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
    assert card.value() == ""


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
    assert card.value() == ""


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
    card._fallback.setText("5")
    assert card.value() == 5
    card.reset()
    assert card._fallback.text() == ""
