"""GhostParameterCard: the Inspector's read-only card for a selected REF_ONLY
row -- a parameter some pinned reference has and the main document does not.

No draft, no input widget: just the parameter's name and the ledger
(:class:`~.reference_block.ReferenceLedger`, shared with ``ParameterCard``'s
own reference section so the two can never drift), one row per distinct
reference value with "Use this value" always offered -- there is no main-file value for
any of them to be "the same" as. Mirrors ``ValidationEmptyState``'s "never
dirty" contract (a class-level ``is_dirty``/``is_editable``) so the
Inspector's undo guard (which reads ``is_dirty``) and the test driver's
editability reads treat it the same as any other non-``ParameterCard`` card.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.compare import ValueGroup
from core.parameter_types import ParameterKind, split_name_and_unit

from ..parameter_row import value_preview
from ..reference_identity import ReferencePin
from ..style import VALUE_INPUT_MAX_WIDTH
from .page import page_content, page_header
from .reference_block import ReferenceLedger
from .spread_scale import scale_for

#: The kinds whose main editor would show a unit label are the only ones
#: whose value box is capped to the standard input width here -- with no main
#: editor on screen to mirror, that cap is what keeps a lone scalar from
#: stretching the full pane.
_CAPPED_KINDS = (ParameterKind.SCALAR, ParameterKind.INTEGER)


class GhostParameterCard(QWidget):
    """Purely informational: no draft, no commit, no context menu."""

    #: See the module docstring: this card holds no editable draft, so the
    #: Inspector's undo guard (``has_focused_draft``, which checks
    #: ``card.is_dirty`` on whatever ``_card`` currently is) always reads it
    #: as having nothing to lose.
    is_dirty = False
    is_editable = False

    #: A ledger row's "Pull", carrying the first-pinned index of that row's
    #: reference group. ``InspectorPanel`` wires this to a ``PullParameter``
    #: command that adds a brand new parameter to the main document, naming
    #: the reference it came from.
    pull_requested = Signal(int)

    def __init__(
        self,
        section_path: tuple[str, ...],
        key: str,
        groups: tuple[ValueGroup, ...],
        pins: list[ReferencePin],
        kind: ParameterKind,
        *,
        read_only: bool = False,
    ) -> None:
        super().__init__()
        #: Retained so a caller handling ``pull_requested`` can resolve the
        #: full parameter path (``section_path + (key,)``) without the
        #: Inspector having to remember it separately.
        self.section_path = section_path
        self.key = key
        # Same page anatomy as ``ParameterCard`` (structured-page layout):
        # identity in the header block, the value rows in the content column.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header_frame, header_box = page_header()

        self._heading = QLabel("Not in the main file")
        self._heading.setObjectName("GhostCardHeading")
        header_box.addWidget(self._heading)

        name, unit = split_name_and_unit(key)
        self._title = QLabel(f"{name} [{unit}]" if unit else name)
        self._title.setObjectName("CardTitle")
        header_box.addWidget(self._title)
        layout.addWidget(header_frame)

        body, body_layout = page_content()
        # On a read-only main the reference value stays a visible fact, but
        # "Use this value" would write to the document, so it is not offered.
        self._ledger = ReferenceLedger(pull_enabled=not read_only)
        self._ledger.pull_requested.connect(self.pull_requested)
        body_layout.addWidget(self._ledger)
        layout.addWidget(body)

        # Every group here is REF_ONLY, so none can equal main and every row
        # offers Pull -- the ledger reads that off ``ValueGroup.equals_main``,
        # which ``compare()`` already set False for these rows.
        monospace = any(isinstance(group.value, str) for group in groups)
        texts = [
            group.value if isinstance(group.value, str) else value_preview(group.value, kind)[0]
            for group in groups
        ]
        width = VALUE_INPUT_MAX_WIDTH if kind in _CAPPED_KINDS else None
        self._ledger.set_rows(
            groups,
            pins,
            texts,
            width=width,
            monospace=monospace,
        )
        # The same spread scale a ParameterCard shows, with no main marker:
        # nothing here has a main value to anchor to, so the axis says only
        # how far the references sit from each other. Two references stating
        # one value still hide it, exactly as elsewhere.
        self._ledger.set_spread(
            scale_for(None, groups, len(pins), kind), pins, width=width
        )

        layout.addStretch(1)
