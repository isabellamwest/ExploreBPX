"""ComparisonStrip: slim reference-aware band atop the parameter list.

Visible only while a reference is docked -- with none docked it stays
hidden and renders nothing, so the Editor is pixel-for-pixel today's, per
the milestone's explicit contract. Purely a display widget: it holds no
comparison state of its own between calls, so ``MainWindow`` (the single
place computing that state) stays the one source of truth.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.compare import ComparisonResult
from state.reference_snapshot import ReferenceSnapshot


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


class ComparisonStrip(QWidget):
    """One-line band: the docked reference's identity + whole-file diff
    counts."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ComparisonStrip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self._identity = QLabel()
        self._identity.setObjectName("ComparisonStripIdentity")
        layout.addWidget(self._identity)

        self._counts = QLabel()
        self._counts.setObjectName("ComparisonStripCounts")
        layout.addWidget(self._counts)

        layout.addStretch(1)

        self.hide()  # no reference docked yet

    def set_state(
        self,
        reference: ReferenceSnapshot | None,
        comparison: ComparisonResult | None,
    ) -> None:
        """Render for the current reference/comparison state, or hide the
        strip entirely when no reference is docked."""
        if reference is None:
            self.hide()
            return
        self.show()
        self._identity.setText(f"Reference · {reference.filename} · {reference.model or '-'}")
        self._counts.setText(_counts_text(comparison) if comparison is not None else "")
