"""Command orchestration: request -> capability check -> execute -> result.

The service is the only place that knows how a :mod:`core.commands` intent maps
onto :mod:`core.editing` primitives or :mod:`core.document_factory`. It performs
preconditions via :mod:`core.structure`, never mutates in place, and returns a
:class:`core.commands.CommandResult` the session applies. Validation stays the
sole job of :mod:`core.bpx_gateway`, so the service produces candidate raw dicts
and lets the document rebuild revalidate.
"""

from __future__ import annotations

import copy

from . import editing, structure
from .commands import (
    AddParameter,
    AddSection,
    ChangeModel,
    Command,
    CommandResult,
    CreateDocument,
    DuplicateParameter,
    MoveParameter,
    Preview,
    PullParameter,
    PullSection,
    RemoveParameter,
    RemoveSection,
    RenameKey,
    SetValue,
    SetValues,
)
from . import document_factory


class CommandError(Exception):
    """Raised when a command cannot be executed in the current document."""


def preview(raw: dict, command: Command) -> Preview:
    """Describe what ``command`` would change, without executing it."""
    if isinstance(command, SetValue):
        return Preview("Set value", (command.path,))
    if isinstance(command, SetValues):
        return Preview(command.label, tuple(path for path, _ in command.updates))
    if isinstance(command, ChangeModel):
        changed = (("Header", "Model"),) + _sections_to_add(raw, command.model)
        return Preview("Change model", changed)
    if isinstance(command, AddSection):
        return Preview("Add section", (command.parent_path + (command.key,),))
    if isinstance(command, RemoveSection):
        warn = () if not raw_at(raw, command.path) else ("Section is not empty.",)
        return Preview("Remove section", (command.path,), warn)
    if isinstance(command, RenameKey):
        new_path = command.path[:-1] + (command.new_key,)
        return Preview("Rename", (command.path, new_path))
    if isinstance(command, AddParameter):
        return Preview("Add parameter", (command.parent_path + (command.key,),))
    if isinstance(command, RemoveParameter):
        return Preview("Remove parameter", (command.path,))
    if isinstance(command, MoveParameter):
        return Preview(f"Move {command.direction}", (command.parent_path + (command.key,),))
    if isinstance(command, DuplicateParameter):
        return Preview("Duplicate parameter", (command.parent_path + (command.key,),))
    if isinstance(command, CreateDocument):
        return Preview(f"New {command.model}")
    raise CommandError(f"Unsupported command: {type(command).__name__}")


def execute(raw: dict, command: Command) -> CommandResult:
    """Run ``command`` against ``raw`` and return the new document state."""
    if isinstance(command, SetValue):
        new = editing.set_value(raw, command.path, command.value)
        return CommandResult(new, "Set value", command.path[:-1], command.path)
    if isinstance(command, SetValues):
        if not command.updates:
            raise CommandError("Nothing to set.")
        new = editing.set_values(raw, command.updates)
        first = command.updates[0][0]
        return CommandResult(new, command.label, first[:-1], first)
    if isinstance(command, PullParameter):
        updates = _pull_updates(raw, command.path, command.value)
        new = editing.set_values(raw, updates)
        return CommandResult(
            new, f'Copy up "{command.path[-1]}"', command.path[:-1], command.path
        )
    if isinstance(command, PullSection):
        updates = _pull_updates(raw, command.path, command.value)
        new = editing.set_values(raw, updates)
        return CommandResult(new, f'Copy up "{command.path[-1]}"', command.path)
    if isinstance(command, ChangeModel):
        updates = ((("Header", "Model"), command.model),) + tuple(
            (path, {}) for path in _sections_to_add(raw, command.model)
        )
        new = editing.set_values(raw, updates)
        return CommandResult(
            new, "Change model", ("Header",), ("Header", "Model")
        )
    if isinstance(command, AddSection):
        new = editing.add_section(raw, command.parent_path, command.key)
        path = command.parent_path + (command.key,)
        return CommandResult(new, "Add section", path)
    if isinstance(command, RemoveSection):
        if not structure.can_remove(command.path):
            raise CommandError("This section cannot be removed.")
        new = editing.remove_section(raw, command.path)
        return CommandResult(new, "Remove section", command.path[:-1])
    if isinstance(command, RenameKey):
        if not structure.can_rename_parameter(command.path, raw_at(raw, command.path)):
            raise CommandError("This name cannot be changed.")
        new_key = command.new_key.strip()
        if not new_key:
            raise CommandError("Name cannot be empty.")
        if new_key == command.path[-1]:
            raise CommandError("Name is unchanged.")
        parent = raw_at(raw, command.path[:-1])
        if isinstance(parent, dict) and new_key in parent:
            raise CommandError(f"“{new_key}” already exists here.")
        new = editing.rename_key(raw, command.path, new_key)
        return CommandResult(new, "Rename", command.path[:-1] + (new_key,))
    if isinstance(command, AddParameter):
        new = editing.add_parameter(raw, command.parent_path, command.key, command.value)
        return CommandResult(new, "Add parameter", command.parent_path, command.parent_path + (command.key,))
    if isinstance(command, RemoveParameter):
        new = editing.remove_parameter(raw, command.path)
        return CommandResult(new, "Remove parameter", command.path[:-1])
    if isinstance(command, MoveParameter):
        if command.direction not in ("up", "down"):
            raise CommandError(f"Unknown move direction: {command.direction!r}")
        parent = raw_at(raw, command.parent_path)
        if not isinstance(parent, dict) or command.key not in parent:
            raise CommandError("This parameter no longer exists.")
        keys = list(parent)
        index = keys.index(command.key)
        if command.direction == "up" and index == 0:
            raise CommandError(f"“{command.key}” is already first.")
        if command.direction == "down" and index == len(keys) - 1:
            raise CommandError(f"“{command.key}” is already last.")
        path = command.parent_path + (command.key,)
        new = editing.move_key(raw, path, command.direction)
        return CommandResult(new, f"Move {command.direction}", command.parent_path, path)
    if isinstance(command, DuplicateParameter):
        path = command.parent_path + (command.key,)
        if not structure.can_duplicate_parameter(path, raw_at(raw, path)):
            raise CommandError("This parameter cannot be duplicated.")
        new, new_key = editing.duplicate_key(raw, path)
        new_path = command.parent_path + (new_key,)
        return CommandResult(new, "Duplicate parameter", command.parent_path, new_path)
    if isinstance(command, CreateDocument):
        new = document_factory.create(command.model, command.title)
        return CommandResult(new, f"New {command.model}", ("Header",))
    raise CommandError(f"Unsupported command: {type(command).__name__}")


def raw_at(raw: dict, path: tuple[str, ...]) -> object:
    """Return the value at ``path``, or ``None`` if absent."""
    node: object = raw
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _missing_ancestors(raw: dict, path: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Ancestor section paths of ``path`` absent from ``raw``, parents-first.

    Walks each successive prefix of ``path`` (excluding ``path`` itself,
    which the caller sets separately). Once a prefix is found missing, every
    deeper prefix is assumed missing too without checking ``raw`` again --
    correct because the caller (``_pull_updates``) applies this list, in
    order, into one ``editing.set_values`` batch: the earlier entry will
    have created that parent by the time the deeper one is written.
    """
    missing: list[tuple[str, ...]] = []
    node: object = raw
    for depth in range(1, len(path)):
        prefix = path[:depth]
        key = path[depth - 1]
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            missing.append(prefix)
            node = {}
    return tuple(missing)


def _pull_updates(
    raw: dict, path: tuple[str, ...], value: object
) -> tuple[tuple[tuple[str, ...], object], ...]:
    """The parents-first ``set_values`` batch for a "Copy up" pull
    (``PullParameter``/``PullSection``): any missing ancestor section as an
    empty object, then ``path`` itself set to a deep copy of ``value``.

    The deep copy matters: ``value`` comes from a frozen
    ``ReferenceSnapshot``'s raw dict, and the main document must never end up
    aliasing it -- a later edit to the pulled value must not silently rewrite
    the reference too.
    """
    ancestors = tuple((ancestor, {}) for ancestor in _missing_ancestors(raw, path))
    return ancestors + ((path, copy.deepcopy(value)),)


def _sections_to_add(raw: dict, model: str) -> tuple[tuple[str, ...], ...]:
    """The required sections *model* expects that ``raw`` does not have.

    Requirements come from :func:`structure.required_sections` (the same
    authority the new-document factory uses), returned parents-first, so a
    sequential batch creates a missing parent before its child. Defensive on
    two fronts: an existing section is never touched, whatever it holds (a
    non-dict there is the validator's to report, not ours to overwrite), and a
    child under a broken (non-dict, non-added) parent is skipped rather than
    failing the whole model change.
    """
    if model not in document_factory.SUPPORTED_MODELS:
        # An unknown model string is still *set* (never gatekept; the
        # validator judges it), but no structure is presumed for it.
        return ()
    added: set[tuple[str, ...]] = set()
    out: list[tuple[str, ...]] = []
    for path in structure.required_sections(model):
        if raw_at(raw, path) is not None:
            continue
        parent = path[:-1]
        if parent and parent not in added and not isinstance(raw_at(raw, parent), dict):
            continue
        added.add(path)
        out.append(path)
    return tuple(out)
