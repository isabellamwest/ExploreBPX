"""GhostParameterCard: the Inspector's read-only card for a selected REF_ONLY
row -- a parameter at least one pinned reference has and the main document
does not.

No draft, no input widget: just the parameter's name and its reference
ledger (:class:`~.reference_block.ReferenceLedger`, shared with
``ParameterCard``'s own reference section so the two can never drift) --
one row per distinct reference value, each with Pull always available:
there is no main-file value for any group to be "the same" as. Mirrors
``ValidationEmptyState``'s "never dirty" contract (a class-level
``is_dirty``/``is_editable``) so the Inspector's undo guard (which reads
``is_dirty``) and the test driver's editability reads treat it the same as
any other non-``ParameterCard`` card.
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
from .reference_block import LedgerRowSpec, ReferenceLedger

#: See ``parameter_card._UNIT_LABEL_KINDS``: the same kinds whose main
#: editor shows a unit label are the only ones whose reference rows show one.
_UNIT_LABEL_KINDS = (ParameterKind.SCALAR, ParameterKind.INTEGER)


class GhostParameterCard(QWidget):
    """Purely informational: no draft, no commit, no context menu."""

    #: See the module docstring: this card holds no editable draft, so the
    #: Inspector's undo guard (``has_focused_draft``, which checks
    #: ``card.is_dirty`` on whatever ``_card`` currently is) always reads it
    #: as having nothing to lose.
    is_dirty = False
    is_editable = False

    #: A ledger row's "Pull", carrying that row's ``ValueGroup``, forwarded
    #: verbatim from the (shared) ledger. ``InspectorPanel`` wires this to a
    #: source-named ``PullParameter`` command that adds a brand new
    #: parameter to the main document.
    pull_requested = Signal(object)

    def __init__(
        self,
        section_path: tuple[str, ...],
        key: str,
        groups: tuple[ValueGroup, ...],
        pins: list[ReferencePin],
        kind: ParameterKind,
    ) -> None:
        super().__init__()
        #: Retained so a caller handling ``pull_requested`` can resolve
        #: the full parameter path (``section_path + (key,)``) without the
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
        self._reference_ledger = ReferenceLedger()
        self._reference_ledger.pull_requested.connect(self.pull_requested)
        body_layout.addWidget(self._reference_ledger)
        layout.addWidget(body)

        row_unit = unit if kind in _UNIT_LABEL_KINDS else ""
        # ``same`` is always False here: a REF_ONLY key has no main-file
        # value for any group to equal, so every row offers Pull. With no
        # main editor to mirror, the capped kinds fall back to the standard
        # input cap. Ghost rows keep the one-line preview for every kind --
        # the differing-table grid belongs to the editing card, where there
        # is a main table to diff against.
        self._reference_ledger.set_rows(
            [
                LedgerRowSpec(
                    pins=tuple(pins[index] for index in group.indices),
                    text=value_preview(group.value, kind)[0],
                    monospace=False,
                    same=False,
                    unit=row_unit,
                    width=VALUE_INPUT_MAX_WIDTH if kind in _UNIT_LABEL_KINDS else None,
                    table=None,
                    group=group,
                )
                for group in groups
            ]
        )

        layout.addStretch(1)
