"""Base class for editing cards.

A card edits a *draft* of one parameter value. It never touches the document;
it emits ``draft_changed`` so the inspector can validate live, and exposes
``value()`` so the inspector can commit on Apply.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from core.bpx_gateway import FieldMeta
from core.tree_model import ParameterItem


class EditorCard(QWidget):
    """Abstract value editor for a single :class:`ParameterItem`."""

    draft_changed = Signal()

    def __init__(self, parameter: ParameterItem, meta: FieldMeta | None) -> None:
        super().__init__()
        self.parameter = parameter
        self.meta = meta
        self._original = parameter.value

    def value(self) -> object:
        """Return the current draft value in raw-dict form."""
        raise NotImplementedError

    def reset(self) -> None:
        """Restore the editor to the original (last committed) value."""
        raise NotImplementedError

    @property
    def is_editable(self) -> bool:
        return True
