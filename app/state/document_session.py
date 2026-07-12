"""Per-document session state (frontend-agnostic).

DocumentSession owns all state associated with a single open BPX document:
the document itself, navigation selection, undo history, dirty flag and
backing-file path.

DocumentSession has no Qt dependencies and no knowledge of the application
shell."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core import bpx_gateway, command_service, editing, export
from core.bpx_gateway import ValidationResult
from core.commands import ChangeModel, Command, Preview, SetValue
from core.document import BPXDocument
from core.tree_model import ParameterItem, TreeNode
from core.validation import ValidatorDiagnostic


@dataclass(frozen=True)
class _HistoryEntry:
    """One undo step: the document *and* where the user was when it was made.

    Selection is part of the state a command changes, so restoring a document
    without restoring its selection leaves the user looking at an unrelated
    parameter while an off-screen one silently reverts. Because the selection
    was valid in the document it is stored beside, it is always valid again
    once that document is restored.
    """

    document: BPXDocument
    selected_path: tuple[str, ...] | None
    selected_parameter_path: tuple[str, ...] | None


class DocumentSession:
    """State for one open BPX document.

    A session may be created with no document (``document=None``) when the
    document will be produced by an initial command such as ``CreateDocument``.
    In normal use, sessions are created by ``AppState.open``.

    ``dirty`` is set by any mutation (``execute_command``, ``apply_value``,
    ``undo``) and cleared by ``save``. ``backing_file`` is the path from which
    the document was opened and to which ``save`` writes.
    """

    def __init__(self, document: BPXDocument | None = None) -> None:
        self.document: BPXDocument | None = document
        self.selected_path: tuple[str, ...] | None = None
        self.selected_parameter_path: tuple[str, ...] | None = None
        self._undo_stack: list[_HistoryEntry] = []
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
            self._undo_stack.append(
                _HistoryEntry(
                    self.document, self.selected_path, self.selected_parameter_path
                )
            )
            filename, fmt = self.document.filename, self.document.fmt
        else:
            filename, fmt = "untitled.json", "json"
        self.document = BPXDocument.from_raw(result.raw, filename=filename, fmt=fmt)
        self.dirty = True
        if result.select_path is not None:
            self.selected_path = result.select_path
        self.selected_parameter_path = result.select_parameter_path

    def undo(self) -> None:
        """Restore the previous document state and selection, if any.

        The selection is restored along with the document so undo lands on the
        change it reverted, rather than leaving the user on whatever they
        happen to be looking at while a parameter elsewhere silently changes.
        """
        if self._undo_stack:
            entry = self._undo_stack.pop()
            self.document = entry.document
            self.selected_path = entry.selected_path
            self.selected_parameter_path = entry.selected_parameter_path
            self.dirty = True

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

    def preview_parameter_issues(
        self, path: tuple[str, ...], value: object
    ) -> list[ValidatorDiagnostic]:
        """Validate a candidate edit and return only *this parameter's* issues.

        The whole document is revalidated (a parameter's legality can depend on
        its siblings), but the result is scoped to the diagnostics that attach
        to ``path``. Document- and object-level issues -- a Header deprecation
        warning, say -- are deliberately excluded: they belong to the Validation
        workspace, not to a parameter's validity badge or Issues tab (see the
        Validation section of docs/03-features.md).

        A full candidate :class:`BPXDocument` is derived rather than
        suffix-matching the raw diagnostics here, so live preview attaches
        issues through exactly the same path-matching as the committed rebuild
        and the two can never disagree about what belongs to a parameter.
        """
        if self.document is None:
            raise ValueError("No document loaded")
        candidate = editing.set_value(self.document.raw, path, value)
        preview = BPXDocument.from_raw(
            candidate, filename=self.document.filename, fmt=self.document.fmt
        )
        parameter = preview.find_parameter(tuple(path))
        return list(parameter.issues) if parameter is not None else []

    def apply_value(self, path: tuple[str, ...], value: object) -> None:
        """Commit an edit as an undoable command.

        A value edit is a document mutation like any other, so it travels the
        same command spine as add/remove: ``execute_command`` rebuilds the
        document, records undo history and marks the session dirty, and the
        edited parameter stays selected.

        One value edit carries structural meaning: committing a string to
        ``Header.Model`` *is* a model change, so it routes to ``ChangeModel``,
        which also adds the target model's required-but-missing sections
        (empty) in the same undo step. A non-string committed there stays a
        plain ``SetValue`` -- it is never gatekept, but no structure is
        presumed for it either; the validator reports it.
        """
        if self.document is None:
            raise ValueError("No document loaded")
        if tuple(path) == ("Header", "Model") and isinstance(value, str):
            self.execute_command(ChangeModel(value))
            return
        self.execute_command(SetValue(tuple(path), value))

    def save(self) -> None:
        """Write the current document to ``backing_file`` and clear dirty.

        The output format is derived from the backing file's extension so
        that the written bytes always match the file's declared type.

        Raises ``ValueError`` if no document is loaded or no backing file
        is set. Raises ``OSError`` if the write fails.
        """
        if self.document is None:
            raise ValueError("No document loaded")
        if self.backing_file is None:
            raise ValueError("No backing file set; use export to save to a new location")
        name = self.backing_file.name.lower()
        fmt = "yaml" if name.endswith((".yml", ".yaml")) else "json"
        self.backing_file.write_bytes(export.to_bytes(self.document.raw, fmt))
        self.dirty = False
