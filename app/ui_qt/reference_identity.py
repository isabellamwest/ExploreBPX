"""Reference identity: the badge every pinned reference is known by.

A pinned reference wears the same two-letter badge in the same colour on
every surface that mentions it -- the Workspace row, the comparison strip
chip, the card ledger's badge cluster, the chart legend, the spread scale's
ticks. That consistency is the whole point: the badge is how a value in a
card is traced back to the file it came from without the file's name having
to be repeated beside every number.

Identity is derived from **pin order**, never stored: colour is
``style.REFERENCE_BADGES[index]`` and the letters are recomputed for the
whole list on every pin change (removing an earlier pin
shifts the later colours, and no extra state exists to go stale). The
letters are the identity of last resort: colour alone must never be the
only thing telling two references apart, which is why every badge carries
them.

:func:`badge_letters` is pure and Qt-free so it can be tested as arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.compare import ComparisonResult
from state.reference_snapshot import ReferenceSnapshot

from . import style

#: Shown when a display name has no letters or digits at all to draw on --
#: a badge must still be a badge, and the row beside it carries the name.
_NO_LETTERS = "?"


def badge_colour(index: int) -> str:
    """The badge colour for the reference pinned at *index*.

    Wraps rather than raising, so a caller that somehow holds an index past
    the cap still paints something instead of crashing the paint pass.
    """
    return style.REFERENCE_BADGES[index % len(style.REFERENCE_BADGES)]


def _initials(name: str) -> str:
    """The first two letters/digits of *name*, first one capitalised.

    Case is otherwise preserved from the source, so "OKane2022" keeps its
    "OK" rather than being flattened to "Ok" -- an all-caps name is a
    deliberate spelling by whoever named the file or the library set.
    """
    letters = [character for character in name if character.isalnum()][:2]
    if not letters:
        return _NO_LETTERS
    return letters[0].upper() + "".join(letters[1:])


def badge_letters(names: Sequence[str]) -> list[str]:
    """The badge letters for *names*, in pin order.

    Ordinarily the first two alphanumerics of the display name. When two or
    more names would produce the same pair, **every** member of that group
    falls back to its first letter plus its 1-based pin ordinal ("C1", "C3")
    -- both, not just the later one, since "Ch" beside "C3" would leave the
    first badge still claiming to stand for a name it no longer uniquely
    identifies.
    """
    initials = [_initials(name) for name in names]
    counts: dict[str, int] = {}
    for pair in initials:
        counts[pair] = counts.get(pair, 0) + 1
    return [
        pair if counts[pair] == 1 else f"{pair[0]}{index + 1}"
        for index, pair in enumerate(initials)
    ]


@dataclass(frozen=True)
class ReferencePin:
    """One pinned reference plus everything the UI needs to render it: its
    snapshot, its comparison against the current main draft, and the badge
    identity derived from its pin order.

    Threaded through the comparison surfaces as a unit so no widget has to
    re-derive letters or colours (and risk disagreeing with another widget
    about which reference "Ch" is).
    """

    index: int
    snapshot: ReferenceSnapshot
    comparison: ComparisonResult | None
    letters: str
    colour: str

    @property
    def name(self) -> str:
        """The display name -- a file's own name, or a library set's curated
        short title. The same string every surface labels this pin with."""
        return self.snapshot.filename


def build_pins(
    references: Sequence[ReferenceSnapshot],
    comparisons: Sequence[ComparisonResult],
) -> list[ReferencePin]:
    """Pair each pinned reference with its comparison and badge identity.

    *comparisons* is positional against *references* and may be shorter (no
    main document is open, so nothing has been compared): the missing
    entries become ``None`` rather than shortening the list, since a
    reference is still pinned and still shown on the Workspace whether or
    not there is anything to compare it against.
    """
    letters = badge_letters([reference.filename for reference in references])
    return [
        ReferencePin(
            index=index,
            snapshot=reference,
            comparison=comparisons[index] if index < len(comparisons) else None,
            letters=letters[index],
            colour=badge_colour(index),
        )
        for index, reference in enumerate(references)
    ]
