"""Toast: the app's one transient-message overlay widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget

from ui_qt.toast import DISMISS_DELAY_MS, Toast


def test_toast_starts_hidden(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    toast = Toast(parent)

    assert toast.isHidden()


def test_show_message_sets_text_and_shows(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(400, 300)
    toast = Toast(parent)

    toast.show_message("Added file.json as reference")

    assert toast.text() == "Added file.json as reference"
    assert not toast.isHidden()


def test_a_new_message_replaces_the_current_one(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    toast = Toast(parent)

    toast.show_message("First message")
    toast.show_message("Second message")

    assert toast.text() == "Second message"


def test_toast_never_takes_focus(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    toast = Toast(parent)

    from PySide6.QtCore import Qt

    assert toast.focusPolicy() == Qt.NoFocus
    assert toast.testAttribute(Qt.WA_TransparentForMouseEvents)


def test_toast_repositions_on_parent_resize(qtbot):
    # A hidden top-level widget never receives a real QEvent.Resize (Qt only
    # generates one once its platform window exists), so the window must be
    # shown first -- the same reasoning as AppDriver._focus.
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(400, 300)
    parent.show()
    qtbot.waitExposed(parent)
    toast = Toast(parent)
    toast.show_message("Hello")
    first_position = toast.pos()

    parent.resize(800, 300)
    qtbot.wait(10)  # the resize event is posted, not delivered synchronously

    assert toast.pos() != first_position
    # Still horizontally centred in the (now wider) parent.
    assert toast.pos().x() == (parent.width() - toast.width()) // 2


def test_toast_auto_dismisses_after_the_delay(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    toast = Toast(parent)

    toast.show_message("Fleeting")
    assert not toast.isHidden()

    qtbot.wait(DISMISS_DELAY_MS + 200)

    assert toast.isHidden()
