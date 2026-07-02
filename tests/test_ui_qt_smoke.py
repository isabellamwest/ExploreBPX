"""Headless smoke test: the Qt frontend boots and drives a full edit cycle."""

from __future__ import annotations

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui_qt.main_window import MainWindow
from ui_qt.inspector import InspectorPanel
from state.app_state import AppState


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_window_boots_and_edits(valid_spm_path, tmp_path):
    # Use a writable copy so the test session's backing_file never points
    # at the repository example file. Avoids accidental writes on save.
    work = tmp_path / "spm_test.json"
    shutil.copy(valid_spm_path, work)

    _app()
    window = MainWindow()
    window._state.open(work)
    window._refresh_all()
    assert window._state.active.document.is_valid

    path = ("Header", "Model")
    window._jump_to_path(path)
    window._state.active.apply_value(path, "DFN")
    window._on_committed()
    assert window._state.active.document.raw["Header"]["Model"] == "DFN"


def test_inspector_reset_clears_invalid_draft_badge(valid_spm_path):
    _app()
    state = AppState()
    state.open(valid_spm_path)
    assert state.active.document.is_valid

    path = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    parameter = state.active.document.find_parameter(path)
    assert parameter is not None
    original = parameter.value

    inspector = InspectorPanel(state)
    inspector.show_parameter(parameter)
    assert inspector._badge.text() == "Valid"

    inspector._card._edit.setText("not-a-number")
    inspector._validate_draft()
    assert inspector._badge.text() == "Invalid"

    inspector._card._on_inline_reset()
    assert inspector._card.value() == original
    assert inspector._badge.text() == "Valid"


def test_inspector_reset_restores_committed_invalid_badge(valid_spm_path):
    _app()
    state = AppState()
    state.open(valid_spm_path)

    path = ("Header", "Model")
    state.active.apply_value(path, "not-a-model")
    assert not state.active.document.is_valid

    parameter = state.active.document.find_parameter(path)
    assert parameter is not None
    assert parameter.has_errors

    inspector = InspectorPanel(state)
    inspector.show_parameter(parameter)
    assert inspector._badge.text() == "Invalid"

    inspector._card._select("SPM")
    inspector._validate_draft()
    assert inspector._badge.text() == "Valid"

    inspector._card._on_inline_reset()
    assert inspector._card.value() == "not-a-model"
    assert inspector._badge.text() == "Invalid"


# ---------------------------------------------------------------------------
# Editor recovery: invalid committed values must not trap the user
# ---------------------------------------------------------------------------

def test_float_field_with_committed_string_opens_scalar_card(valid_spm_path):
    """A string committed to a plain float field must reopen as a ScalarCard.

    Before the fix, classify() would route the string value to FUNCTION, which
    maps to ReadOnlyCard. The user was then trapped: the value was visible but
    neither editable nor resettable.
    """
    from ui_qt.cards.scalar import ScalarCard
    from core.parameter_types import ParameterKind

    _app()
    state = AppState()
    state.open(valid_spm_path)

    path = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    state.active.apply_value(path, "not-a-number")

    parameter = state.active.document.find_parameter(path)
    assert parameter is not None
    assert parameter.kind == ParameterKind.SCALAR, (
        f"Expected SCALAR after committing string to float field, got {parameter.kind}"
    )
    assert parameter.has_errors

    inspector = InspectorPanel(state)
    inspector.show_parameter(parameter)
    assert isinstance(inspector._card, ScalarCard), (
        f"Expected ScalarCard for invalid float field, got {type(inspector._card).__name__}"
    )
    assert inspector._badge.text() == "Invalid"

    # The card must be editable: entering a valid value should clear the badge.
    inspector._card._edit.setText("5.0")
    inspector._validate_draft()
    assert inspector._badge.text() == "Valid"

    # Reset must restore the committed (invalid) raw value.
    inspector._card._on_inline_reset()
    assert inspector._card.value() == "not-a-number"
    assert inspector._badge.text() == "Invalid"


def _find_any_integer_parameter(document):
    """Return the path and ParameterItem of the first INTEGER parameter in the tree."""
    from core.parameter_types import ParameterKind

    def _walk(node):
        for p in node.parameters:
            if p.kind == ParameterKind.INTEGER:
                return p
        for child in node.children:
            result = _walk(child)
            if result is not None:
                return result
        return None

    return _walk(document.tree)


def test_integer_field_with_committed_string_opens_integer_card(valid_spm_path):
    """A string committed to an integer field must reopen as an IntegerCard with fallback.

    The IntegerCard should display the raw string, remain editable, and allow
    Reset to restore the committed value.
    """
    from ui_qt.cards.integer import IntegerCard
    from core.parameter_types import ParameterKind

    _app()
    state = AppState()
    state.open(valid_spm_path)

    original_param = _find_any_integer_parameter(state.active.document)
    if original_param is None:
        pytest.skip("No INTEGER parameter found in the test fixture")

    path = original_param.path

    state.active.apply_value(path, "not-an-integer")

    parameter = state.active.document.find_parameter(path)
    assert parameter is not None
    assert parameter.kind == ParameterKind.INTEGER, (
        f"Expected INTEGER after committing string to integer field, got {parameter.kind}"
    )
    assert parameter.has_errors

    inspector = InspectorPanel(state)
    inspector.show_parameter(parameter)
    assert isinstance(inspector._card, IntegerCard), (
        f"Expected IntegerCard for invalid integer field, got {type(inspector._card).__name__}"
    )
    # Fallback path: QSpinBox should NOT be active when original is not a valid int.
    assert inspector._card._spin is None
    assert inspector._card._fallback is not None
    assert inspector._card._fallback.text() == "not-an-integer"
    assert inspector._badge.text() == "Invalid"

    # Reset must restore the raw committed string.
    inspector._card._on_inline_reset()
    assert inspector._card.value() == "not-an-integer"
    assert inspector._badge.text() == "Invalid"
