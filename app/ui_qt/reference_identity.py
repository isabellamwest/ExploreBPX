"""Stable visual identity for pinned references (multi-reference track,
Phase 1).

Every pinned reference carries the same identity on every surface -- the
Workspace pin rows, the comparison strip's chips, the Card Ledger's badge
clusters and (Phase 2) the chart overlay legend: a two-letter badge on a
colour assigned by pin order. Identity is *derived*, never stored: letters
and colours are recomputed from the current pin list on every change
(decision D1: colour = current list index, so removing an earlier pin
shifts later colours -- no extra state to persist or reconcile).

The composite the surfaces consume is :class:`ReferencePin`: the snapshot,
its comparison against the main document (``None`` with no document open),
and the derived letters/colour/display name. ``MainWindow`` builds the list
via :func:`build_pins` and threads it to every consumer, so no widget ever
derives identity on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from core.compare import ComparisonResult
from state.reference_snapshot import ReferenceSnapshot

from . import typography
from .style import REFERENCE_BADGE_COLOURS

#: Badge diameters: the Workspace pin row's regular mark and the compact
#: mark every denser surface uses (strip chips, ledger clusters, legend).
BADGE_SIZE = 20
BADGE_SIZE_SMALL = 17


def display_name(snapshot: ReferenceSnapshot) -> str:
    """The short name a pin is known by everywhere: chips, pin rows, undo
    labels (`Pull "<key>" from Chen2020`).

    A library set's ``filename`` is its curated short title with the cell
    identity in parentheses ("Chen2020 (LG M50 21700)") -- the parenthetical
    is dropped here, chip-length names being the point. A file reference
    uses its file name without the extension ("my_cell.json" -> "my_cell").
    """
    if snapshot.set_id is not None:
        return snapshot.filename.split(" (")[0].strip() or snapshot.filename
    return Path(snapshot.filename).stem or snapshot.filename


def badge_letters(names: list[str]) -> list[str]:
    """Two-character badge letters for *names*, in pin order. Pure.

    A name's natural letters are its first two characters, first character
    uppercased, second kept as-is ("Chen2020" -> "Ch", "OKane2022" -> "OK",
    "AE-LFP" -> "AE"). When two pins' natural letters collide, every member
    of the collision falls back to first letter + pin ordinal (1-based), so
    no two badges ever read the same. Recomputed per pin change, never
    persisted -- letters may legitimately change when a pin is removed.
    """
    def natural(name: str) -> str:
        name = name.strip()
        if len(name) >= 2:
            return name[0].upper() + name[1]
        if name:
            return name[0].upper()
        return "R"

    naturals = [natural(name) for name in names]
    letters = []
    for index, candidate in enumerate(naturals):
        if naturals.count(candidate) > 1:
            letters.append(f"{candidate[0]}{index + 1}")
        else:
            letters.append(candidate)
    return letters


@dataclass(frozen=True)
class ReferencePin:
    """One pinned reference with its derived identity, as threaded to every
    comparison-aware surface."""

    snapshot: ReferenceSnapshot
    #: This pin's comparison against the main document; ``None`` with no
    #: document open (the pin list itself outlives the document).
    comparison: ComparisonResult | None
    #: Chip-length display name -- see :func:`display_name`.
    name: str
    #: Two-character badge letters -- see :func:`badge_letters`.
    letters: str
    #: Badge colour hex, ``REFERENCE_BADGE_COLOURS[pin index]``.
    colour: str


def badge_label(pin: ReferencePin, *, small: bool = False) -> QLabel:
    """The circular two-letter badge for *pin* -- the one rendering every
    surface shares, so a badge can never drift between the Workspace, the
    strip and the ledger. White semibold letters on the pin's own colour;
    the letters double as the accessible identity (colour is never the only
    encoding). Inline stylesheet on purpose: the colour is per-pin data, not
    a static QSS class.
    """
    size = BADGE_SIZE_SMALL if small else BADGE_SIZE
    label = QLabel(pin.letters)
    label.setObjectName("ReferenceBadge")
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignCenter)
    label.setFont(typography.ui_font(typography.MICRO, weight=typography.SEMIBOLD))
    label.setStyleSheet(
        f"background-color: {pin.colour}; color: #ffffff;"
        f" border-radius: {size // 2}px;"
    )
    label.setToolTip(pin.name)
    return label


def build_pins(
    references: list[ReferenceSnapshot],
    comparisons: list[ComparisonResult],
) -> list[ReferencePin]:
    """Derive the full pin-identity list from the current state.

    *comparisons* is positional (one per reference, the order
    ``MainWindow._recompute_comparison`` builds); a shorter/empty list --
    no document open, or a caller running before the recompute -- yields
    ``comparison=None`` for the unmatched tail rather than misaligning.
    """
    names = [display_name(snapshot) for snapshot in references]
    letters = badge_letters(names)
    return [
        ReferencePin(
            snapshot=snapshot,
            comparison=comparisons[index] if index < len(comparisons) else None,
            name=names[index],
            letters=letters[index],
            colour=REFERENCE_BADGE_COLOURS[index],
        )
        for index, snapshot in enumerate(references)
    ]
