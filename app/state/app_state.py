"""Application state container (frontend-agnostic).

Holds the currently open document, the selected object-node path, and the
selected parameter path (when a single parameter is being inspected in detail).
It contains no UI-framework code so it can be reused by any frontend. The UI
layer is responsible for owning and persisting an instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core import bpx_gateway, command_service, editing
from core.bpx_gateway import ValidationResult
from core.commands import Command, Preview
from core.document import BPXDocument
from core.tree_model import ParameterItem, TreeNode


@dataclass
class AppState:
    """The full application state for a single open BPX file.

    ``document`` is singular for V1. A future multi-file version can replace it
    with a collection without changing the UI's interaction with this class.

    Navigation is two-tiered: ``selected_path`` points at the visible object
    node (whose parameter list is shown), and ``selected_parameter_path`` points
    at a single parameter within it (whose detail view is shown). A ``None``
    parameter path means the object's parameter list is shown rather than a
    parameter detail.
    """

    document: BPXDocument | None = None
    selected_path: tuple[str, ...] | None = None
    selected_parameter_path: tuple[str, ...] | None = None
    _undo_stack: list[BPXDocument] = field(default_factory=list, repr=False)

    @property
    def has_document(self) -> bool:
        return self.document is not None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def preview_command(self, command: Command) -> Preview:
        """Describe a command's effect without executing it."""
        if self.document is None:
            raise ValueError("No document loaded")
        return command_service.preview(self.document.raw, command)

    def execute_command(self, command: Command) -> None:
        """Run a command, rebuild the document, and record undo history."""
        raw = {} if self.document is None else self.document.raw
        result = command_service.execute(raw, command)
        if self.document is not None:
            self._undo_stack.append(self.document)
            filename, fmt = self.document.filename, self.document.fmt
        else:
            filename, fmt = "untitled.json", "json"
        self.document = BPXDocument.from_raw(result.raw, filename=filename, fmt=fmt)
        if result.select_path is not None:
            self.selected_path = result.select_path
        self.selected_parameter_path = result.select_parameter_path

    def undo(self) -> None:
        """Restore the previous document state, if any."""
        if self._undo_stack:
            self.document = self._undo_stack.pop()

    def load(self, data: bytes | str, filename: str) -> None:
        """Open a file, replacing any current document and selection."""
        self.document = BPXDocument.from_bytes(data, filename)
        self.selected_path = None
        self.selected_parameter_path = None
        self._undo_stack.clear()

    def clear(self) -> None:
        self.document = None
        self.selected_path = None
        self.selected_parameter_path = None
        self._undo_stack.clear()

    def select(self, path: tuple[str, ...]) -> None:
        """Select an object node and show its parameter list."""
        self.selected_path = tuple(path)
        self.selected_parameter_path = None

    def select_parameter(self, path: tuple[str, ...]) -> None:
        """Select a parameter and show its detail view.

        The owning object remains selected so the breadcrumb and a click on an
        object segment resolve correctly.
        """
        self.selected_parameter_path = tuple(path)

    def selected_node(self) -> TreeNode | None:
        if self.document is None or self.selected_path is None:
            return None
        return self.document.find(self.selected_path)

    def selected_parameter(self) -> ParameterItem | None:
        if self.document is None or self.selected_parameter_path is None:
            return None
        return self.document.find_parameter(self.selected_parameter_path)

    def preview_value(
        self, path: tuple[str, ...], value: object
    ) -> ValidationResult:
        """Validate a candidate edit without committing it (live preview).

        Builds a copy of the raw dict with ``value`` set at ``path`` and runs
        the backend validator on it. The document is left untouched, so a card
        can show live feedback while the user edits a draft.
        """
        if self.document is None:
            raise ValueError("No document loaded")
        candidate = editing.set_value(self.document.raw, path, value)
        return bpx_gateway.validate(candidate)

    def apply_value(self, path: tuple[str, ...], value: object) -> None:
        """Commit an edit: mutate the raw dict, rebuild tree, revalidate.

        The visible selection is preserved so the UI stays on the parameter the
        user just changed.
        """
        if self.document is None:
            raise ValueError("No document loaded")
        raw = editing.set_value(self.document.raw, path, value)
        self.document = BPXDocument.from_raw(
            raw, filename=self.document.filename, fmt=self.document.fmt
        )
