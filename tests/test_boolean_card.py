"""Tests for BooleanCard: the checkbox editor for ``ParameterKind.BOOLEAN``."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.boolean import BooleanCard


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _param(value: bool) -> ParameterItem:
    return ParameterItem(label="Flag", path=("Header", "Flag"), kind=ParameterKind.BOOLEAN, value=value)


def test_round_trips_true():
    _app()
    card = BooleanCard(_param(True), None)
    assert card._check.isChecked() is True
    assert card.value() is True


def test_round_trips_false():
    _app()
    card = BooleanCard(_param(False), None)
    assert card._check.isChecked() is False
    assert card.value() is False


def test_label_text_is_lowercase_true_false():
    _app()
    card = BooleanCard(_param(False), None)
    assert card._check.text() == "false"
    card._check.setChecked(True)
    assert card._check.text() == "true"


def test_toggling_emits_draft_changed():
    _app()
    card = BooleanCard(_param(False), None)
    received = []
    card.draft_changed.connect(lambda: received.append(True))
    card._check.setChecked(True)
    assert received == [True]


def test_a_user_click_commits_immediately():
    """A checkbox toggle is a complete, discrete act: clicking commits without
    a further Enter (the draft still fires first, so the commit sees it)."""
    _app()
    card = BooleanCard(_param(False), None)
    order = []
    card.draft_changed.connect(lambda: order.append("draft"))
    card.commit_requested.connect(lambda: order.append("commit"))
    card._check.click()
    assert order == ["draft", "commit"]
    assert card.value() is True


def test_a_programmatic_setchecked_does_not_commit():
    """Seeding/reset go through setChecked; only a real user click commits."""
    _app()
    card = BooleanCard(_param(False), None)
    received = []
    card.commit_requested.connect(lambda: received.append(True))
    card._check.setChecked(True)
    card.reset()
    assert received == []


def test_reset_restores_original():
    _app()
    card = BooleanCard(_param(True), None)
    card._check.setChecked(False)
    assert card.value() is False
    card.reset()
    assert card.value() is True
    assert card._check.text() == "true"


def test_enter_commits_via_keyboard_handler():
    _app()
    card = BooleanCard(_param(True), None)
    received = []
    card.commit_requested.connect(lambda: received.append(True))
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    card.eventFilter(card._check, event)
    assert received == [True]


def test_escape_reverts_via_keyboard_handler():
    _app()
    card = BooleanCard(_param(True), None)
    card._check.setChecked(False)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    card.eventFilter(card._check, event)
    assert card.value() is True
