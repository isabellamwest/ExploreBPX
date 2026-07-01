"""Per-document session state (frontend-agnostic).

DocumentSession owns all state associated with a single open BPX document:
the document itself, navigation selection, undo history, and (reserved for the
forthcoming Save vs Export step) dirty flag and backing-file path.

DocumentSession has no Qt dependencies and no knowledge of the application
shell.
"""

from __future__ import annotations

from pathlib import Path

from core import bpx_gateway, command_service, editing
from core.bpx_gateway import ValidationResult
from core.commands import Command, Preview
from core.document import BPXDocument
from core.tree_model import ParameterItem, TreeNode


class DocumentSession:
    """State for one open BPX document.

    A session may be created with no document (``document=None``) when the
    document will be produced by an initial command such as ``CreateDocument``.
    In normal use, sessions are created by ``AppState.open``.

    ``dirty`` and ``backing_file`` are reserved for the forthcoming Save vs
    Export implementation and are not yet wired to any behaviour.
    """

    def __init__(self, document: BPXDocument | None = None) -> None:
        self.document: BPXDocument | None = document
        self.selected_path: tuple[str, ...] | None = None
        self.selected_parameter_path: tuple[str, ...] | None = None
        self._undo_stack: list[BPXDocument] = []
        # Reserved: wired in the Save vs Export implementation step.
        self.dirty: bool = False
        self.backing_file: Path | None = None

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
