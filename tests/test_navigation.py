"""Unit tests for the NavigationService resolution and notification contract.

The service owns navigation state and requests only: it resolves a target path,
updates the session selection and emits a single ``navigated`` notification. It
performs no reveal behaviour (that belongs to subscribing views), so these tests
assert only on the resolved target and the selection state.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from explore_bpx.state.app_state import AppState
from explore_bpx.ui_qt.navigation import NavigationService

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
_CELL = ("Parameterisation", "Cell")


@pytest.fixture
def service(qtbot, valid_spm_path):
    state = AppState()
    state.open(valid_spm_path)
    return NavigationService(state), state


def test_navigate_resolves_a_parameter_target(service):
    nav, state = service
    received = []
    nav.navigated.connect(received.append)

    nav.navigate(_CAPACITY)

    assert len(received) == 1
    target = received[0]
    assert target.parameter_path == _CAPACITY
    assert target.parameter is not None
    assert target.object_path == _CELL
    assert state.active.selected_parameter_path == _CAPACITY
    assert state.active.selected_path == _CELL


def test_navigate_resolves_an_object_target(service):
    nav, state = service
    received = []
    nav.navigated.connect(received.append)

    nav.navigate(_CELL)

    assert len(received) == 1
    target = received[0]
    assert target.object_path == _CELL
    assert target.parameter is None
    assert target.parameter_path is None
    assert state.active.selected_path == _CELL
    assert state.active.selected_parameter_path is None


def test_navigate_is_a_noop_without_a_document(qtbot):
    nav = NavigationService(AppState())
    received = []
    nav.navigated.connect(received.append)

    nav.navigate(_CAPACITY)

    assert received == []


def test_navigate_ignores_an_empty_path(service):
    nav, _state = service
    received = []
    nav.navigated.connect(received.append)

    nav.navigate(())

    assert received == []
