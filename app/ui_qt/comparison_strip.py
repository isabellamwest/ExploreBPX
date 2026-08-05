"""ComparisonStrip: slim reference-aware band atop the parameter list.

Visible only while at least one reference is pinned -- with none it stays
hidden and renders nothing, so the Editor is pixel-for-pixel today's, per
the milestone's explicit contract. Purely a display widget: it holds no
comparison state of its own between calls, so ``MainWindow`` (the single
place computing that state) stays the one source of truth.

Multi-reference (design rule 2): the strip is fully quiet -- one identity
chip per pinned reference (badge + name), in pin order, with no counts or
controls inline. Each chip's tooltip carries that reference's own
whole-file counts. When the strip is too narrow for every name it elides
all chips to badges only; it never wraps to a second line.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.compare import ComparisonResult

from . import style
from .reference_identity import ReferencePin, badge_label


def _counts_text(comparison: ComparisonResult) -> str:
    """"14 differ · 8 ref only" -- singular forms at 1, a zero side omitted
    entirely, "no differences" when both are zero (M2 brief)."""
    differ = comparison.differ_count
    ref_only = comparison.ref_only_count
    parts = []
    if differ:
        parts.append("1 differs" if differ == 1 else f"{differ} differ")
    if ref_only:
        parts.append(f"{ref_only} ref only")
    return " · ".join(parts) if parts else "no differences"


def _chip_tooltip(pin: ReferencePin) -> str:
    """"Marquis2019 · SPM · 21 differ · 6 ref only" -- identity first, then
    the counts the strip itself stays quiet about; no counts segment at all
    with no document open (there is no comparison to count)."""
    parts = [pin.name, pin.snapshot.model or "-"]
    if pin.comparison is not None:
        parts.append(_counts_text(pin.comparison))
    return " · ".join(parts)


class _ReferenceChip(QWidget):
    """One pin's identity chip: the shared badge beside its display name.

    The name label is what elision hides (`set_elided`); the badge always
    stays, so a narrow strip still shows every pin's identity mark.
    """

    def __init__(self, pin: ReferencePin) -> None:
        super().__init__()
        self.setObjectName("ComparisonStripChip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(badge_label(pin, small=True))
        self._name = QLabel(pin.name)
        self._name.setObjectName("ComparisonStripChipName")
        layout.addWidget(self._name)
        self.setToolTip(_chip_tooltip(pin))

    def set_elided(self, elided: bool) -> None:
        self._name.setVisible(not elided)

    def full_width(self) -> int:
        """The chip's natural width with its name shown -- measured from
        hints, not the current (possibly name-hidden) geometry."""
        badge_width = self.layout().itemAt(0).widget().sizeHint().width()
        return badge_width + self.layout().spacing() + self._name.sizeHint().width()


class ComparisonStrip(QWidget):
    """One-line band of pinned-reference identity chips."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ComparisonStrip")
        layout = QHBoxLayout(self)
        # Left/right inset matches the section header wash directly above it
        # (``ui_qt.group_box.TintedSection``'s gutter) so the two stacked
        # washes' text lines up; top/bottom stay slim.
        layout.setContentsMargins(style.SPACING_LG, style.SPACING_XS, style.SPACING_LG, style.SPACING_XS)
        layout.setSpacing(style.SPACING_MD)
        self._chip_layout = layout
        self._chips: list[_ReferenceChip] = []
        layout.addStretch(1)

        self.hide()  # no reference pinned yet

    def set_state(self, pins: list[ReferencePin]) -> None:
        """Rebuild the chips for the current pin list, or hide the strip
        entirely when no reference is pinned. Chips are rebuilt wholesale --
        identity (letters/colour) can change with any pin change, so there
        is nothing worth diffing in place.
        """
        for chip in self._chips:
            self._chip_layout.removeWidget(chip)
            # Hidden before deleteLater: a removed widget keeps painting at
            # its old geometry until deferred deletion runs.
            chip.hide()
            chip.deleteLater()
        self._chips = []
        if not pins:
            self.hide()
            return
        for index, pin in enumerate(pins):
            chip = _ReferenceChip(pin)
            self._chip_layout.insertWidget(index, chip)
            self._chips.append(chip)
        self.show()
        self._update_elision()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._update_elision()

    def _update_elision(self) -> None:
        """Names shown while every full chip fits, badges-only otherwise --
        all together (a half-elided strip would misread as two kinds of
        pin). The strip itself never wraps."""
        if not self._chips:
            return
        margins = self._chip_layout.contentsMargins()
        available = self.width() - margins.left() - margins.right()
        spacing = self._chip_layout.spacing() * (len(self._chips) - 1)
        needed = sum(chip.full_width() for chip in self._chips) + spacing
        elided = needed > available
        for chip in self._chips:
            chip.set_elided(elided)
