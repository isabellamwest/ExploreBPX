"""Shared section chrome: bordered cards and full-bleed tinted washes.

:class:`GroupBox` is one bordered, rounded frame whose first row is a
shaded header band (caps title, an optional suffix widget snug against it,
an optional trailing widget flush right past the stretch) over a body
layout the caller fills freely. This is the "IDE panel" language reused,
previously, by three independent copies: the Diagnostics Issues/
Outstanding boxes, the reference-library dialog's detail card, and (until
Phase 3) the Workspace document/reference cards.

:class:`TintedSection` is the newer, borderless sibling: a full-width
tinted wash with the same caps-title/suffix header over a measure-capped
body, no frame at all -- the Workspace page's document/reference sections.

This module owns chrome only -- badges, content-hugging lists and similar
concerns stay in whichever module needs them, layered on top via
:attr:`GroupBox.body_layout`/:attr:`TintedSection.body_layout` (or
subclassing).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import style
from .typography import panel_title

#: The two visual variants, keyed to their QSS selectors in style.py: a
#: neutral grey band (Diagnostics' Issues/Outstanding boxes) or the
#: reference purple band (the reference-library dialog's detail card).
#: "reference" keeps its own historical object name since it already
#: carries its own purple QSS pair; "neutral" is the shared name that once
#: replaced the byte-identical WorkspaceGroupBox/DiagnosticsGroupBox pair
#: (the Workspace page has since moved to :class:`TintedSection`).
_FRAME_OBJECT_NAMES = {"neutral": "GroupBox", "reference": "ReferenceGroupBox"}
_HEADER_OBJECT_NAMES = {"neutral": "GroupBoxHeader", "reference": "ReferenceGroupBoxHeader"}


class GroupBox(QFrame):
    """One banded-header group box (see module docstring)."""

    def __init__(
        self,
        title: str,
        *,
        variant: str = "neutral",
        title_object_name: str = "PanelTitle",
        title_widget: QLabel | None = None,
        suffix: QWidget | None = None,
        trailing: QWidget | None = None,
        header_styled_background: bool = True,
        header_margins: tuple[int, int, int, int] = (12, 5, 12, 5),
        header_spacing: int | None = 8,
        body_margins: tuple[int, int, int, int] = (12, 10, 12, 12),
        body_spacing: int = 8,
        body_stretch: int = 0,
    ) -> None:
        """*suffix* sits immediately after the title, no stretch between
        them (Diagnostics' ratio text, e.g. "3 of 6"); *trailing* sits
        flush right, after the header's stretch (the reference-library
        dialog's "Read-only" tag, or Diagnostics' badge row). Both are optional and
        independent -- a caller can pass either, neither, or both.
        ``header_styled_background`` mirrors each call site's existing
        ``WA_StyledBackground`` use exactly (Diagnostics' header band never
        set it, so its migration passes ``False``, to keep rendering
        pixel-identical). ``header_spacing=None`` leaves Qt's own style
        default in place instead of forcing one (Diagnostics' original
        header never called ``setSpacing`` either). ``title_widget`` lets a
        caller supply its own pre-built label instead of the caps
        ``panel_title`` tier -- the reference-library dialog's detail
        heading is plain sentence-case text set later via ``setText``, not
        chrome the app itself titles, so it never went through
        ``panel_title``'s caps/letter-spacing treatment."""
        super().__init__()
        self.setObjectName(_FRAME_OBJECT_NAMES[variant])
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName(_HEADER_OBJECT_NAMES[variant])
        if header_styled_background:
            header.setAttribute(Qt.WA_StyledBackground, True)
        self.header_layout = QHBoxLayout(header)
        self.header_layout.setContentsMargins(*header_margins)
        if header_spacing is not None:
            self.header_layout.setSpacing(header_spacing)

        self.title_label = title_widget if title_widget is not None else panel_title(
            title, object_name=title_object_name
        )
        self.header_layout.addWidget(self.title_label)
        if suffix is not None:
            self.header_layout.addWidget(suffix)
        self.header_layout.addStretch(1)
        if trailing is not None:
            self.header_layout.addWidget(trailing)
        outer.addWidget(header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(*body_margins)
        self.body_layout.setSpacing(body_spacing)
        outer.addWidget(self.body, body_stretch)


#: The gutter every :class:`TintedSection` title/body shares -- the same
#: 16px left/right inset a suffix sits 16px from the right edge, matching
#: this module's docstring exactly.
_SECTION_GUTTER = 16

#: The disclosure chevrons a collapsible section's title row carries --
#: the same pair the Diagnostics fold headers draw, so "this heading
#: toggles" reads identically everywhere.
_CHEVRON_EXPANDED = "▾"
_CHEVRON_COLLAPSED = "▸"


class _MeasureBoundVBox(QVBoxLayout):
    """A :class:`TintedSection`'s outer column, height-computed at the width
    its content is actually arranged at.

    The section stretches full-bleed while its header and body are capped at
    the section's measure -- and Qt asks this layout for height at the
    *full* width (``QWidgetItem::heightForWidth`` consults a widget's layout
    directly, bypassing any widget-level override). At a wide window that
    computes label wrapping at a width the capped children never receive,
    so a section whose wrapped content grows after first layout is handed
    too few pixels and clips it (geometry-probed on screen: the record's
    expanded fact details lost exactly the shortfall). Both height queries
    therefore clamp to the measure plus this layout's own margins -- the
    width the children genuinely see. The measure is passed in, not read
    back off the parent widget, so a section that takes a wider measure
    keeps its height computed at the width its own children see."""

    def __init__(self, parent: QWidget, measure: int) -> None:
        super().__init__(parent)
        self._measure = measure

    def _bound(self, width: int) -> int:
        margins = self.contentsMargins()
        return min(width, self._measure + margins.left() + margins.right())

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt naming
        return super().heightForWidth(self._bound(width))

    def minimumHeightForWidth(self, width: int) -> int:  # noqa: N802 - Qt naming
        return super().minimumHeightForWidth(self._bound(width))


class _ClickableRow(QWidget):
    """A plain row widget that emits ``clicked`` on a left press -- the hit
    area for a collapsible :class:`TintedSection`'s whole title row (title,
    chevron and the empty stretch between them), not just the text.

    A signal, deliberately not a stored callback: holding the section's
    bound method here would tie the whole widget tree into a pure-Python
    reference cycle, deferring its death from prompt refcounting to a later
    GC pass -- which can land mid-event-dispatch and delete live Qt objects
    under Qt's feet (PySide keeps QObject slot references weak, so the
    signal creates no such cycle).
    """

    clicked = Signal()

    def __init__(self, clickable: bool) -> None:
        super().__init__()
        self._clickable = clickable

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()
            return
        super().mousePressEvent(event)


class TintedSection(QWidget):
    """One full-width tinted section wash: a caps title row (optional
    right-aligned suffix) over a measure-capped body. Unlike
    :class:`GroupBox` there is no border, corner radius or shadow -- the
    wash colour itself is the section's only chrome, for pages built as
    full-bleed stacked bands rather than floating bordered cards (the
    Workspace page's document/reference sections, the Inspector's Issues/
    Documentation sections).

    ``object_name`` selects the wash colour: this module never spells a
    colour literal, so pair one with a ``QWidget#<object_name>``
    background rule in style.py (see ``WorkspaceMainSection``/
    ``WorkspaceReferenceSection`` for the pattern). The body is capped at
    ``measure`` (``style.CONTENT_MEASURE`` by default), left-hugging the
    same gutter as the title, the same left-unset/no-alignment idiom
    ``cards/page.py`` uses. A section whose body is a horizontal row of
    cards rather than running text passes a wider ``measure``: the reading
    measure that keeps prose legible squeezes side-by-side cards until
    their labels elide.

    ``collapsible=True`` puts a disclosure chevron before the title and
    makes the whole title row a click target that toggles the body
    (:meth:`set_collapsed`); collapsed, the section is just its tinted
    title band. The open/collapsed state is the widget's own -- a caller
    that keeps one section resident across content changes keeps the
    user's choice for free.
    """

    def __init__(
        self,
        title: str,
        *,
        object_name: str,
        title_object_name: str = "PanelTitle",
        suffix: QWidget | None = None,
        collapsible: bool = False,
        measure: int = style.CONTENT_MEASURE,
    ) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._collapsed = False

        outer = _MeasureBoundVBox(self, measure)
        outer.setContentsMargins(_SECTION_GUTTER, 12, _SECTION_GUTTER, 12)
        outer.setSpacing(8)

        self.header = _ClickableRow(collapsible)
        if collapsible:
            self.header.clicked.connect(self._toggle_collapsed)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self._chevron: QLabel | None = None
        if collapsible:
            self.header.setCursor(Qt.PointingHandCursor)
            # Same caps-tier object name as the title so the chevron takes
            # the identical muted colour/size from QSS.
            self._chevron = QLabel(_CHEVRON_EXPANDED)
            self._chevron.setObjectName(title_object_name)
        if self._chevron is not None:
            header.addWidget(self._chevron)
        self.title_label = panel_title(title, object_name=title_object_name)
        header.addWidget(self.title_label)
        header.addStretch(1)
        if suffix is not None:
            header.addWidget(suffix)
        # The header shares the body's measure rather than the full bleed.
        # Right-aligned across a wide window the suffix drifted hundreds of
        # pixels from the content it annotates ("Read-only" adrift of the
        # reference rows, "3 warnings" adrift of the document it counts);
        # capped, the title and its suffix are the bookends of the same
        # column the body fills.
        self.header.setMaximumWidth(measure)
        outer.addWidget(self.header)

        self.body = QWidget()
        self.body.setMaximumWidth(measure)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        outer.addWidget(self.body)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        """Show/hide the body and flip the chevron. Harmless (body toggle
        only) on a non-collapsible section, though callers have no reason
        to do that."""
        self._collapsed = collapsed
        self.body.setVisible(not collapsed)
        if self._chevron is not None:
            self._chevron.setText(_CHEVRON_COLLAPSED if collapsed else _CHEVRON_EXPANDED)

    def _toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)


class TintedSectionHeader(QWidget):
    """:class:`TintedSection`'s header row on its own -- a full-width tinted
    wash carrying only the caps-title/suffix row, no body beneath it. For a
    column too narrow to also cap a body at ``style.CONTENT_MEASURE`` (the
    parameter-list pane's section header): same wash, same caps-title/
    right-aligned-suffix anatomy as :class:`TintedSection`, just without a
    body -- the caller owns everything below it.
    """

    def __init__(
        self,
        title: str,
        *,
        object_name: str,
        title_object_name: str = "PanelTitle",
        suffix: QWidget | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_SECTION_GUTTER, 8, _SECTION_GUTTER, 8)
        layout.setSpacing(8)
        self.title_label = panel_title(title, object_name=title_object_name)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        if suffix is not None:
            layout.addWidget(suffix)

    def set_title(self, title: str) -> None:
        """Update the caps title text in place (``panel_title`` uppercases
        it), for a header whose section changes after construction."""
        self.title_label.setText(title.upper())
