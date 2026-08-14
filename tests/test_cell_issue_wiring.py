"""Wiring: validator diagnostics reach the grid via ``Card.set_cell_issues``.

The pure ``cell_issues`` mapping is tested in isolation in
``test_cell_issues.py``; this file threads it through the card/body layer and
the Inspector's three push seams -- ``show_parameter``, ``_validate_draft``,
``_on_reset`` -- against a real document and a real BPX validation run, so a
defect in any one seam shows up as a genuinely untinted (or wrongly tinted)
cell rather than a mocked assertion.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from state.app_state import AppState
from ui_qt.cards.function import FunctionCard
from ui_qt.cards.registry import create_card
from ui_qt.inspector import InspectorPanel

_TIME = ("Validation", "C/20 discharge", "Time [s]")
_DIFFUSIVITY = ("Parameterisation", "Negative electrode", "Diffusivity [m2.s-1]")


@pytest.fixture(autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _panel_on(qtbot, path, workfile):
    state = AppState()
    state.open(workfile)
    session = state.active
    session.select(path[:-1])
    session.select_parameter(path)

    panel = InspectorPanel(state)
    qtbot.addWidget(panel)
    panel.show_parameter(session.selected_parameter())
    return state, panel


def _grid_model(panel):
    """The active SeriesCard's grid model, reaching through ParameterCard."""
    return panel._card._editor._grid._model


def test_show_parameter_tints_a_committed_bad_element(qtbot, tmp_path, valid_spm_dict):
    """A parameter selected with an already-invalid element (committed state)
    is tinted immediately, from ``parameter.issues`` -- no edit required."""
    doc = dict(valid_spm_dict)
    doc["Validation"] = {
        "C/20 discharge": {
            "Time [s]": [0, "oops", 200],
            "Current [A]": [-0.6, -0.6, -0.6],
            "Voltage [V]": [4.1, 4.0, 3.9],
            "Temperature [K]": [298.15, 298.15, 298.15],
        }
    }
    workfile = tmp_path / "bad_time.json"
    workfile.write_text(json.dumps(doc), encoding="utf-8")

    _state, panel = _panel_on(qtbot, _TIME, workfile)

    model = _grid_model(panel)
    assert model.data(model.index(1, 0), Qt.BackgroundRole) is not None
    assert model.data(model.index(1, 0), Qt.ToolTipRole)
    assert model.data(model.index(0, 0), Qt.BackgroundRole) is None


def test_live_edit_tints_the_cell_after_validate_draft(qtbot, spm_with_validation_path):
    """Typing a bad value and running the live-preview validation (the
    Inspector's debounced ``_validate_draft``) tints the offending cell."""
    _state, panel = _panel_on(qtbot, _TIME, spm_with_validation_path)
    model = _grid_model(panel)
    assert model.data(model.index(1, 0), Qt.BackgroundRole) is None

    model.setData(model.index(1, 0), "oops", Qt.EditRole)
    panel._validate_draft()

    assert model.data(model.index(1, 0), Qt.BackgroundRole) is not None
    assert model.data(model.index(1, 0), Qt.ToolTipRole)


def test_reset_restores_committed_tint_state(qtbot, spm_with_validation_path):
    """Escape (``_on_reset``) restores the committed issues, clearing a live
    preview tint after the draft that caused it is discarded."""
    _state, panel = _panel_on(qtbot, _TIME, spm_with_validation_path)
    model = _grid_model(panel)

    model.setData(model.index(1, 0), "oops", Qt.EditRole)
    panel._validate_draft()
    assert model.data(model.index(1, 0), Qt.BackgroundRole) is not None

    panel._card._editor.reset()
    panel._on_reset()

    assert model.data(model.index(1, 0), Qt.BackgroundRole) is None


def _table_grid_model(panel):
    """The active TableBody's grid model, reaching through ParameterCard/ModalCard."""
    return panel._card._editor._body._grid._model


def test_show_parameter_tints_a_committed_bad_table_cell(qtbot, tmp_path, valid_spm_dict):
    """An InterpolatedTable parameter (FunctionCard's table mode) selected with
    an already-invalid y-cell is tinted immediately, mirroring the series case."""
    doc = dict(valid_spm_dict)
    doc["Parameterisation"]["Negative electrode"]["Diffusivity [m2.s-1]"] = {
        "x": [0, 1, 2],
        "y": [1e-14, "oops", 1e-14],
    }
    workfile = tmp_path / "bad_table.json"
    workfile.write_text(json.dumps(doc), encoding="utf-8")

    _state, panel = _panel_on(qtbot, _DIFFUSIVITY, workfile)

    model = _table_grid_model(panel)
    assert model.data(model.index(1, 1), Qt.BackgroundRole) is not None  # y, row 1
    assert model.data(model.index(1, 1), Qt.ToolTipRole)
    assert model.data(model.index(1, 0), Qt.BackgroundRole) is None  # x, same row
    assert model.data(model.index(0, 1), Qt.BackgroundRole) is None  # y, other row


def test_live_edit_tints_the_table_cell_after_validate_draft(qtbot, tmp_path, valid_spm_dict):
    """Typing a bad y value and running the live-preview validation (the
    Inspector's debounced ``_validate_draft``) tints the offending cell in the
    table grid, through the same seam as the series case."""
    doc = dict(valid_spm_dict)
    doc["Parameterisation"]["Negative electrode"]["Diffusivity [m2.s-1]"] = {
        "x": [0, 1, 2],
        "y": [1e-14, 2e-14, 3e-14],
    }
    workfile = tmp_path / "good_table.json"
    workfile.write_text(json.dumps(doc), encoding="utf-8")

    _state, panel = _panel_on(qtbot, _DIFFUSIVITY, workfile)
    model = _table_grid_model(panel)
    assert model.data(model.index(1, 1), Qt.BackgroundRole) is None

    model.setData(model.index(1, 1), "oops", Qt.EditRole)
    panel._validate_draft()

    assert model.data(model.index(1, 1), Qt.BackgroundRole) is not None
    assert model.data(model.index(1, 1), Qt.ToolTipRole)


def test_modal_card_in_a_non_grid_mode_noops_on_set_cell_issues():
    """A ModalCard's active mode with no grid (``FloatInt``) must not crash,
    and must never reach into another mode's hidden grid."""
    param = ParameterItem(
        label="Diffusivity [m2.s-1]",
        path=("Parameterisation", "Negative electrode", "Diffusivity [m2.s-1]"),
        kind=ParameterKind.FUNCTION,
        value=3.7,
        unit="m2.s-1",
    )
    card = create_card(param, None)
    assert isinstance(card, FunctionCard)
    assert card.current_mode == "FloatInt"

    card.set_cell_issues([])  # must not raise; the active body has no grid

    # The inactive InterpolatedTable mode's grid stays untouched (empty, no
    # issues ever pushed to it) -- confirming the delegation really is scoped
    # to the active body alone.
    table_mode = next(m for m in card._modes if m.label == "InterpolatedTable")
    assert table_mode.body._grid._model.issues() == {}
