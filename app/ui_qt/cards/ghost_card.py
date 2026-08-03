"""GhostParameterCard: the Inspector's read-only card for a selected REF_ONLY
row (multi-file track M2) -- a parameter the docked reference has and the
main document does not.

No draft, no input widget: just the parameter's name and its "Reference
file" heading + value row (:class:`~.reference_block.ReferenceValueBlock`,
shared with ``ParameterCard``'s own reference section so the two can never
drift), Copy up always enabled -- there is no main-file value to be "the
same" as. Mirrors ``ValidationEmptyState``'s "never dirty" contract (a
class-level ``is_dirty``/``is_editable``) so the Inspector's undo guard
(which reads ``is_dirty``) and the test driver's editability reads treat it
the same as any other non-``ParameterCard`` card.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.parameter_types import ParameterKind, split_name_and_unit

from ..parameter_row import value_preview
from .page import page_content, page_header
from .reference_block import ReferenceValueBlock

#: See ``parameter_card._UNIT_LABEL_KINDS``: the same kinds whose main
#: editor shows a unit label are the only ones whose reference row shows one.
_UNIT_LABEL_KINDS = (ParameterKind.SCALAR, ParameterKind.INTEGER)


class GhostParameterCard(QWidget):
    """Purely informational: no draft, no commit, no context menu."""

    #: See the module docstring: this card holds no editable draft, so the
    #: Inspector's undo guard (``has_focused_draft``, which checks
    #: ``card.is_dirty`` on whatever ``_card`` currently is) always reads it
    #: as having nothing to lose.
    is_dirty = False
    is_editable = False

    #: The reference row's "Copy up" button, forwarded verbatim from the
    #: (shared) reference block. ``InspectorPanel`` wires this to a
    #: ``PullParameter`` command that adds a brand new parameter to the main
    #: document (multi-file track M3).
    copy_up_requested = Signal()

    def __init__(
        self,
        section_path: tuple[str, ...],
        key: str,
        ref_value: object,
        kind: ParameterKind,
    ) -> None:
        super().__init__()
        #: Retained so a caller handling ``copy_up_requested`` can resolve
        #: the full parameter path (``section_path + (key,)``) without the
        #: Inspector having to remember it separately.
        self.section_path = section_path
        self.key = key
        # Same page anatomy as ``ParameterCard`` (structured-page layout):
        # identity in the header block, the value row in the content column.
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
        self._reference_block = ReferenceValueBlock()
        self._reference_block.copy_up_requested.connect(self.copy_up_requested)
        body_layout.addWidget(self._reference_block)
        layout.addWidget(body)
        text, _ghost = value_preview(ref_value, kind)
        row_unit = unit if kind in _UNIT_LABEL_KINDS else ""
        # same_as_main is always False here: a REF_ONLY row has no main-file
        # value to be "the same" as, so Copy up is always enabled.
        self._reference_block.set_content(
            text, row_unit, same_as_main=False, narrow=kind in _UNIT_LABEL_KINDS
        )

        layout.addStretch(1)
