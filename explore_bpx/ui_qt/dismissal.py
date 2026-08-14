"""Shared click-away dismissal for the app's transient popups.

The app has three frameless, non-modal popups (:class:`~ui_qt.search.SearchPopup`,
:class:`~ui_qt.parameter_info_popover.ParameterInfoPopover`,
:class:`~ui_qt.add_parameter_popup.AddParameterPopup`). All three need the same
conventional behaviour: a mouse press outside the popup dismisses it, and that
dismissing press is *swallowed* -- the widget under the click does not also
receive it, so a second click is required to act on whatever is underneath.

``Qt.Popup`` (a real keyboard/mouse grab) cannot be used for this: the search
box the user types into lives in the main window's top bar, *outside* the
results popup, so a grab would either break typing (keyboard grab) or make the
first click on the box dismiss instead of place the caret (mouse grab). A
non-grab, geometry-based application event filter is required for search
regardless of what the other two popups do, so all three share it rather than
mixing mechanisms.

:class:`OutsideDismissFilter` deliberately hit-tests the event's *global*
position against known widget geometry rather than using
``QApplication.widgetAt`` or a real grab -- geometry is deterministic under the
offscreen Qt platform used in tests; ``widgetAt`` and grabs are not.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect
from PySide6.QtWidgets import QApplication, QWidget


class OutsideDismissFilter(QObject):
    """Hides *popup* on a mouse press outside it, swallowing that press.

    *inside* is an optional tuple of additional widgets (e.g. the search
    box's own ``QLineEdit``, which lives outside the popup's geometry but
    must not trigger dismissal) that count as "inside" alongside the popup
    itself.

    Install with :meth:`install` once the popup is shown. The filter also
    watches the popup itself for ``QEvent.Hide`` and removes itself from the
    application then, and for ``QObject.destroyed`` so a torn-down popup
    never leaves a stale filter registered on ``qApp``.
    """

    def __init__(self, popup: QWidget, inside: tuple[QWidget, ...] = ()) -> None:
        super().__init__(popup)
        self._popup: QWidget | None = popup
        self._inside = inside
        self._installed = False
        popup.installEventFilter(self)
        popup.destroyed.connect(self._on_popup_destroyed)

    # -- lifecycle -----------------------------------------------------
    def install(self) -> None:
        """Register on the application, if not already registered."""
        if self._installed or self._popup is None:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._installed = True

    def remove(self) -> None:
        """Unregister from the application, if currently registered."""
        if not self._installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._installed = False

    def _on_popup_destroyed(self) -> None:
        self.remove()
        self._popup = None

    # -- filtering -------------------------------------------------------
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        event_type = event.type()
        if watched is self._popup and event_type == QEvent.Hide:
            self.remove()
            return False
        if event_type == QEvent.MouseButtonPress:
            return self._handle_press(event)
        if event_type == QEvent.ApplicationDeactivate:
            self._hide_popup()
            return False
        return False

    def _handle_press(self, event) -> bool:
        if self._popup is None:
            return False
        pos = event.globalPosition().toPoint()
        if self._popup.frameGeometry().contains(pos):
            return False
        for widget in self._inside:
            if widget is not None and widget.isVisible() and self._global_rect(widget).contains(pos):
                return False
        self._hide_popup()
        return True

    @staticmethod
    def _global_rect(widget: QWidget) -> QRect:
        top_left = widget.mapToGlobal(widget.rect().topLeft())
        return QRect(top_left, widget.size())

    def _hide_popup(self) -> None:
        if self._popup is not None:
            self._popup.hide()
