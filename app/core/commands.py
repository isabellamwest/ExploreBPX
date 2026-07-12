"""Command requests and results: the document operation vocabulary.

Commands are *intent* objects. They describe what the user wants to do, never
how to do it. The mutation logic stays in :mod:`core.editing`; orchestration
(validate -> preview -> execute -> result) lives in
:mod:`core.command_service`. This keeps three responsibilities apart:

* commands.py  -> intent (this module),
* editing.py   -> raw-dict primitives,
* command_service.py -> lifecycle coordination.

Every command targets the current :class:`core.document.BPXDocument`; the
service returns a :class:`CommandResult` describing the new document and the
selection the UI should move to.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Command:
    """Base class for all document operations (intent only)."""


@dataclass(frozen=True)
class SetValue(Command):
    """Set the leaf value at ``path`` to ``value``."""

    path: tuple[str, ...]
    value: object


@dataclass(frozen=True)
class SetValues(Command):
    """Atomically set several leaf values as **one** operation.

    ``updates`` is an ordered tuple of ``(path, value)`` pairs. The whole batch
    is a single document rebuild and a single undo entry: a CSV import that
    fills four experiment arrays must revert as one step, never as four. The
    *first* update's path is where the UI selection lands afterwards, so
    callers put the parameter the user was editing first.

    ``label`` titles the undo entry (e.g. "Import CSV"); the default matches
    the ``SetValue`` convention.
    """

    updates: tuple[tuple[tuple[str, ...], object], ...]
    label: str = "Set values"


@dataclass(frozen=True)
class AddSection(Command):
    """Add an empty object section ``key`` under ``parent_path``."""

    parent_path: tuple[str, ...]
    key: str


@dataclass(frozen=True)
class RemoveSection(Command):
    """Remove the object section at ``path``."""

    path: tuple[str, ...]


@dataclass(frozen=True)
class RenameKey(Command):
    """Rename the user-named dict key at ``path`` to ``new_key``.

    Only keys the user owns are renamable (Particle material instances,
    Validation runs -- see ``structure.can_rename``); schema property names
    never are. Renaming moves the **address** of every descendant of the
    renamed node: any future address-keyed sidecar metadata (e.g. per-value
    provenance) must cascade here. Values referring to the old name (a
    per-material MAP key) are deliberately *not* rewritten -- the validator
    reports them, the app invents nothing.
    """

    path: tuple[str, ...]
    new_key: str


@dataclass(frozen=True)
class AddParameter(Command):
    """Add a parameter ``key`` with an initial ``value`` under ``parent_path``."""

    parent_path: tuple[str, ...]
    key: str
    value: object


@dataclass(frozen=True)
class RemoveParameter(Command):
    """Remove the parameter at ``path``."""

    path: tuple[str, ...]


@dataclass(frozen=True)
class ChangeModel(Command):
    """Declare the document to be ``model``, completing its structure.

    Sets ``Header.Model`` and, in the same atomic step, adds any section the
    target model requires that is missing -- **empty**, exactly as the
    new-document scaffolds do (structure carries no invented values). Without
    this, a model switch strands the document on one opaque root error
    ("parameter set does not correspond with the model type ..."); with the
    empty sections present, the validator instead reports the actual missing
    parameters, field by field.

    Nothing is ever removed: a section the new model does not know (e.g. a
    populated Electrolyte after DFN -> SPM) stays put, the validator reports
    it as an extra input, and the tree's Remove section -- with its
    populated-content confirmation -- is the deliberate way to drop it.
    """

    model: str


@dataclass(frozen=True)
class CreateDocument(Command):
    """Create a new incomplete structural document for ``model``."""

    model: str
    title: str = ""


@dataclass(frozen=True)
class Preview:
    """A summary of what a command would change, before it is executed."""

    label: str
    changed_paths: tuple[tuple[str, ...], ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandResult:
    """Outcome of executing a command.

    ``raw`` is the new document dict; the session rebuilds the BPXDocument and
    pushes history. ``select_path`` is the object the UI should land on,
    ``select_parameter_path`` the parameter (if any). ``label`` titles the undo
    entry. ``warnings`` carries non-fatal notes (e.g. removed populated section).
    """

    raw: dict
    label: str
    select_path: tuple[str, ...] | None = None
    select_parameter_path: tuple[str, ...] | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
