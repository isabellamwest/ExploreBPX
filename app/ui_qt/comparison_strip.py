"""ComparisonStrip: the pinned references' identity chips in the page bar.

One quiet identity chip per pinned reference -- badge plus name, nothing
else. No counts on the face of it, no controls: the strip's whole job is to
answer "what am I comparing against?" at a glance, and a row of numbers
there would be read as a verdict on the file rather than as bookkeeping.
Per-reference counts live in each chip's tooltip.

Docked in the window's page-header bar, after the page title (it began
life as a band atop the parameter list, where it cost the column a row and
collapsed to bare badges far sooner). Visible only while at least one
reference is pinned *and* the Editor page is current -- the bar is shared
by every page, and Workspace/Source carry their own reference surfaces.
Purely a display widget: it holds no comparison state of its own between
calls, so ``MainWindow`` (the single place computing that state) stays the
one source of truth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from . import badges, style

if TYPE_CHECKING:
    from core.compare import ComparisonResult

    from .reference_identity import ReferencePin


def _counts_text(comparison: ComparisonResult) -> str:
    """ "14 differ · 8 reference only" -- singular forms at 1, a zero side
    omitted entirely, "no differences" when both are zero.
    "Reference" spelled out, never "ref"."""
    differ = comparison.differ_count
    ref_only = comparison.ref_only_count
    parts = []
    if differ:
        parts.append("1 differs" if differ == 1 else f"{differ} differ")
    if ref_only:
        parts.append(f"{ref_only} reference only")
    return " · ".join(parts) if parts else "no differences"


def chip_tooltip(pin: ReferencePin) -> str:
    """ "Chen2020 · DFN · 14 differ · 8 reference only" -- the whole of what the
    chip is not saying out loud. The counts tail is dropped when there is no
    comparison at all (no main document open): a chip must never imply a
    comparison that was never run."""
    parts = [pin.name, pin.snapshot.model or "-"]
    if pin.comparison is not None:
        parts.append(_counts_text(pin.comparison))
    return " · ".join(parts)


class _IdentityChip(QWidget):
    """One pinned reference's chip: its badge beside its name.

    The name label is what disappears when the strip is narrow; the badge
    never does, since it is the identity every other surface shares.
    """

    def __init__(self, pin: ReferencePin) -> None:
        super().__init__()
        self.setObjectName("ComparisonStripChip")
        tooltip = chip_tooltip(pin)
        self.setToolTip(tooltip)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(style.SPACING_XS)

        layout.addWidget(badges.make_reference_badge(pin.letters, pin.colour, tooltip))

        self._name = QLabel(pin.name)
        self._name.setObjectName("ComparisonStripIdentity")
        self._name.setToolTip(tooltip)
        layout.addWidget(self._name)

    def set_name_visible(self, visible: bool) -> None:
        self._name.setVisible(visible)

    def natural_width(self) -> int:
        """The width this chip wants with its name shown -- what the strip
        adds up to decide whether the names fit at all."""
        return badges.REFERENCE_BADGE_SIZE + self.layout().spacing() + self._name.sizeHint().width()


class ComparisonStrip(QWidget):
    """One-line band of identity chips, one per pinned reference."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ComparisonStrip")
        layout = QHBoxLayout(self)
        # Left inset separates the chips from the page title beside them;
        # no right inset (the internal stretch owns the leftover width) and
        # no vertical inset (the 34px bar centres the row itself).
        layout.setContentsMargins(style.SPACING_LG, 0, 0, 0)
        layout.setSpacing(style.SPACING_MD)

        self._chips: list[_IdentityChip] = []
        self._layout = layout
        #: Whether the page the chips describe (the Editor) is current --
        #: the bar itself never goes away, so the chips must.
        self._page_active = True
        layout.addStretch(1)

        self.hide()  # nothing pinned yet

    def set_state(self, pins: list[ReferencePin]) -> None:
        """Render one chip per pinned reference, or hide the strip entirely
        when nothing is pinned.

        Chips are rebuilt wholesale rather than updated in place: pin order
        drives badge identity, so a rebuild is the only way a removal can
        never leave a chip wearing a colour that has moved on.
        """
        for chip in self._chips:
            self._layout.removeWidget(chip)
            chip.setParent(None)
            chip.deleteLater()
        self._chips = []

        if not pins:
            self._refresh_visible()
            return

        for index, pin in enumerate(pins):
            chip = _IdentityChip(pin)
            self._chips.append(chip)
            self._layout.insertWidget(index, chip)
        self._apply_elision()
        self._refresh_visible()

    def set_page_active(self, active: bool) -> None:
        """Tell the strip whether the Editor page is current. Chips render
        only there: on any other page the bar's title stands alone."""
        self._page_active = active
        self._refresh_visible()

    def _refresh_visible(self) -> None:
        self.setVisible(bool(self._chips) and self._page_active)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        """Drop chip names when they do not all fit, keeping badges and one
        line.

        Measured against what the chips actually want rather than a fixed
        breakpoint: the strip takes whatever width the bar has left after
        the page title, where one reference's name always fits and four
        long ones may not. A fixed threshold hid the name even when there
        was room for it. Names go all-or-nothing -- a row where some chips
        are named and some are not reads as an error, not as a fit.
        """
        if not self._chips:
            return
        margins = self._layout.contentsMargins()
        available = self.width() - margins.left() - margins.right()
        if available <= 0:
            return  # not laid out yet; the first resize decides
        needed = sum(chip.natural_width() for chip in self._chips)
        needed += self._layout.spacing() * (len(self._chips) - 1)
        for chip in self._chips:
            chip.set_name_visible(needed <= available)
