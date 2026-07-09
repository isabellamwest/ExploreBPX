"""Tests for the shared click-away dismissal mechanism used by all three of
the app's transient popups (search results, parameter info, add-parameter).

These exercise :class:`~ui_qt.dismissal.OutsideDismissFilter` directly and in
isolation from any real popup widget, using explicit global-position hit
testing rather than a real mouse grab -- see the module docstring in
``ui_qt/dismissal.py`` for why.

Note: :func:`QApplication.processEvents` does *not* deliver
``QEvent.DeferredDelete``; tests that need a widget actually destroyed (not
just scheduled for deletion) must call
``app.sendPostedEvents(None, QEvent.DeferredDelete)``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from ui_qt.dismissal import OutsideDismissFilter


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _press_event(global_pos) -> QMouseEvent:
    return QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(0, 0),
        QPointF(global_pos),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )


def _release_event(global_pos) -> QMouseEvent:
    return QMouseEvent(
        QEvent.MouseButtonRelease,
        QPointF(0, 0),
        QPointF(global_pos),
        Qt.LeftButton,
        Qt.NoButton,
        Qt.NoModifier,
    )


@pytest.fixture
def popup(qtbot) -> QWidget:
    _app()
    w = QWidget()
    w.setGeometry(100, 100, 100, 50)
    qtbot.addWidget(w)
    w.show()
    return w


def test_press_outside_hides_and_swallows(popup):
    filt = OutsideDismissFilter(popup)
    filt.install()

    corner = popup.rect().bottomRight()
    outside = popup.mapToGlobal(corner) + type(corner)(50, 50)
    event = _press_event(outside)
    consumed = _app().sendEvent(popup, event)

    assert popup.isVisible() is False
    assert consumed is True  # eventFilter returned True: the press was swallowed


def test_press_inside_does_not_hide(popup):
    filt = OutsideDismissFilter(popup)
    filt.install()

    inside = popup.mapToGlobal(popup.rect().center())
    event = _press_event(inside)
    _app().sendEvent(popup, event)

    assert popup.isVisible() is True


def test_press_inside_registered_extra_widget_does_not_hide(popup, qtbot):
    extra = QWidget()
    extra.setGeometry(500, 500, 40, 20)
    qtbot.addWidget(extra)
    extra.show()

    filt = OutsideDismissFilter(popup, inside=(extra,))
    filt.install()

    inside_extra = extra.mapToGlobal(extra.rect().center())
    event = _press_event(inside_extra)
    _app().sendEvent(extra, event)

    assert popup.isVisible() is True


def test_application_deactivate_hides_popup(popup):
    filt = OutsideDismissFilter(popup)
    filt.install()

    _app().sendEvent(popup, QEvent(QEvent.ApplicationDeactivate))

    assert popup.isVisible() is False


def test_swallow_proof_button_beneath_does_not_receive_click(popup, qtbot):
    filt = OutsideDismissFilter(popup)
    filt.install()

    button = QPushButton()
    button.setGeometry(500, 500, 60, 20)
    qtbot.addWidget(button)
    button.show()
    clicks = []
    button.clicked.connect(lambda: clicks.append(1))

    global_pos = button.mapToGlobal(button.rect().center())
    _app().sendEvent(button, _press_event(global_pos))
    assert popup.isVisible() is False

    _app().sendEvent(button, _release_event(global_pos))
    assert clicks == []  # the dismissing press never reached the button beneath


def test_stale_filter_removed_on_destroy_no_crash(qtbot):
    app = _app()
    w = QWidget()
    w.setGeometry(100, 100, 100, 50)
    w.show()
    filt = OutsideDismissFilter(w)
    filt.install()

    w.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)

    # A subsequent outside press must not crash or invoke a dead popup, and
    # -- because the stale filter was properly deregistered -- must reach
    # whatever widget is actually beneath it.
    button = QPushButton()
    button.setGeometry(500, 500, 60, 20)
    qtbot.addWidget(button)
    button.show()
    clicks = []
    button.clicked.connect(lambda: clicks.append(1))

    global_pos = button.mapToGlobal(button.rect().center())
    app.sendEvent(button, _press_event(global_pos))
    app.sendEvent(button, _release_event(global_pos))

    assert clicks == [1]


def test_hiding_the_popup_directly_deregisters_the_filter(popup):
    """Calling .hide() on the popup itself (e.g. via Escape) must deregister
    the filter, not just an outside press routed through it."""
    filt = OutsideDismissFilter(popup)
    filt.install()
    assert filt._installed is True

    popup.hide()
    assert filt._installed is False
