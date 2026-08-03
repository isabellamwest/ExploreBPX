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
class _Selection:
    """Which object and, if any, which parameter were showing."""

    path: tuple[str, ...] | None
    parameter_path: tuple[str, ...] | None


@dataclass(frozen=True)
class ParameterPreview:
    """A live-edit preview's verdict on one parameter (see
    :meth:`DocumentSession.preview_parameter`).

    ``validation_completed`` mirrors the candidate document's
    :attr:`core.document.BPXDocument.validation_completed`: when False,
    ``bpx`` aborted before judging this parameter's section, so an empty
    ``issues`` list means *unchecked*, not *clean* -- the badge must not
    read "Valid"."""

    issues: list[ValidatorDiagnostic]
    validation_completed: bool


@dataclass(frozen=True)
class _Transition:
    """One undo/redo step: the document on both sides of a command, and the
    selection each side reveals.

    Selection belongs to the *transition*, not to either document alone: undo
    must land on the change it reverted (``before_selection`` -- the selection
    that was current when the command ran) and redo must land on the change it
    reapplied (``after_selection`` -- the command's own target). Neither of
    those is "whatever the user happens to be looking at" when Undo or Redo is
    pressed, which can differ if they navigated away in between.

    Because the *same* ``_Transition`` object moves between the undo and redo
    stacks (see ``undo``/``redo``), the two selections can never drift apart:
    there is exactly one record of what this command did, not two that must
    be kept in sync by hand.
    """

    before: BPXDocument
    after: BPXDocument
    before_selection: _Selection
    after_selection: _Selection


class DocumentSession:
    """State for one open BPX document.

    A session may be created with no document (``document=None``) when the
    document will be produced by an initial command such as ``CreateDocument``.
    In normal use, sessions are created by ``AppState.open``.

    ``dirty`` is derived, not stored: it compares the current document against
    the one last saved (or opened), so any mutation (``execute_command``,
    ``apply_value``) makes the session dirty and ``save`` cleans it -- and
    undoing back to the save point cleans it too, because undo/redo restore
    the *same* document object a transition recorded. ``backing_file`` is the
    path from which the document was opened and to which ``save`` writes.
    """

    def __init__(self, document: BPXDocument | None = None) -> None:
        self.document: BPXDocument | None = document
        self.selected_path: tuple[str, ...] | None = None
        self.selected_parameter_path: tuple[str, ...] | None = None
        self._undo_stack: list[_Transition] = []
        self._redo_stack: list[_Transition] = []
        self._saved_document: BPXDocument | None = document
        self.backing_file: Path | None = None

    @property
    def dirty(self) -> bool:
        """True when the in-memory document is not the one on disk.

        Identity, not equality: every command produces a fresh
        ``BPXDocument``, while undo/redo restore the exact object a
        transition recorded -- so walking history back to the save point
        yields the saved object itself and the session reads clean again.
        "Modified" always means "what you see is not what is saved", never
        "an edit happened at some point".
        """
        return self.document is not self._saved_document

    @dirty.setter
    def dirty(self, value: bool) -> None:
        """Compatibility setter: ``False`` marks the current document as the
        saved one (what ``save`` means); ``True`` forgets the save marker
        entirely (a never-saved session, e.g. a fresh scaffold)."""
        self._saved_document = None if value else self.document

    @property
    def has_document(self) -> bool:
        return self.document is not None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def _selection(self) -> _Selection:
        """Capture the current selection.

        Shared by ``execute_command``, which uses it to record both sides of
        a transition -- the selection before the command runs, and (after
        applying the command's own result) the selection after.
        """
        return _Selection(self.selected_path, self.selected_parameter_path)

    def preview_command(self, command: Command) -> Preview:
        """Describe a command's effect without executing it."""
        if self.document is None:
            raise ValueError("No document loaded")
        return command_service.preview(self.document.raw, command)

    def execute_command(self, command: Command) -> None:
        """Run a command, rebuild the document, and record undo history.

        A new command branches history: whatever was undone-and-redoable is no
        longer reachable from the document this command produces, so the redo
        stack is cleared. This is the standard rule for a linear undo/redo
        history and it must be explicit here.

        The pushed ``_Transition`` records the selection on *both* sides of
        the command: ``before`` is the selection the user made to reach this
        edit (today's selection, since they must have selected a parameter to
        change it); ``after`` is the command's own target
        (``result.select_path`` / ``result.select_parameter_path``), which is
        what a later redo must land on regardless of where the user has
        navigated to since.
        """
        raw = {} if self.document is None else self.document.raw
        result = command_service.execute(raw, command)
        previous_document = self.document
        if previous_document is not None:
            before_selection = self._selection()
            filename, fmt = previous_document.filename, previous_document.fmt
        else:
            filename, fmt = "untitled.json", "json"
        self._redo_stack.clear()
        self.document = BPXDocument.from_raw(result.raw, filename=filename, fmt=fmt)
        if result.select_path is not None:
            self.selected_path = result.select_path
        self.selected_parameter_path = result.select_parameter_path
        if previous_document is not None:
            self._undo_stack.append(
                _Transition(
                    before=previous_document,
                    after=self.document,
                    before_selection=before_selection,
                    after_selection=self._selection(),
                )
            )

    def undo(self) -> None:
        """Restore the document and selection from before the last command.

        The popped transition already carries the selection that was current
        when the command ran, so undo lands on the change it reverted rather
        than leaving the user on whatever they happen to be looking at while a
        parameter elsewhere silently changes.

        The same transition is pushed onto the redo stack, not a fresh
        snapshot of the current state: that keeps undo and redo permanently in
        agreement about what this command's own selection was.
        """
        if self._undo_stack:
            transition = self._undo_stack.pop()
            self.document = transition.before
            self.selected_path = transition.before_selection.path
            self.selected_parameter_path = transition.before_selection.parameter_path
            self._redo_stack.append(transition)

    def redo(self) -> None:
        """Reapply the most recently undone command and land on its own target.

        The popped transition carries the selection the command itself
        produced (``result.select_path`` / ``result.select_parameter_path`` at
        the time it ran), not whatever the user has navigated to since --
        otherwise redo would reapply a change off-screen. Mirrors ``undo``:
        the same transition object is pushed back onto the undo stack, so a
        further undo returns to exactly the state this redo left.
        """
        if self._redo_stack:
            transition = self._redo_stack.pop()
            self.document = transition.after
            self.selected_path = transition.after_selection.path
            self.selected_parameter_path = transition.after_selection.parameter_path
            self._undo_stack.append(transition)

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

    def preview_parameter(
        self, path: tuple[str, ...], value: object
    ) -> ParameterPreview:
        """Validate a candidate edit and return *this parameter's* verdict.

        The whole document is revalidated (a parameter's legality can depend on
        its siblings), but the result is scoped to the diagnostics that attach
        to ``path``. Document- and object-level issues -- a Header deprecation
        warning, say -- are deliberately excluded: they belong to the Validation
        workspace, not to a parameter's validity badge or Issues tab (see the
        Diagnostics page section of docs/architecture.md).

        A full candidate :class:`BPXDocument` is derived rather than
        suffix-matching the raw diagnostics here, so live preview attaches
        issues through exactly the same path-matching as the committed rebuild
        and the two can never disagree about what belongs to a parameter. The
        candidate's ``validation_completed`` travels with the issues for the
        same reason: whether an empty issue list means *clean* or *unchecked*
        is the candidate document's verdict, not the caller's guess.
        """
        if self.document is None:
            raise ValueError("No document loaded")
        candidate = editing.set_value(self.document.raw, path, value)
        preview = BPXDocument.from_raw(
            candidate, filename=self.document.filename, fmt=self.document.fmt
        )
        parameter = preview.find_parameter(tuple(path))
        return ParameterPreview(
            issues=list(parameter.issues) if parameter is not None else [],
            validation_completed=preview.validation_completed,
        )

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
