"""Command orchestration: request -> capability check -> execute -> result.

The service is the only place that knows how a :mod:`core.commands` intent maps
onto :mod:`core.editing` primitives or :mod:`core.document_factory`. It performs
preconditions via :mod:`core.structure`, never mutates in place, and returns a
:class:`core.commands.CommandResult` the session applies. Validation stays the
sole job of :mod:`core.bpx_gateway`, so the service produces candidate raw dicts
and lets the document rebuild revalidate.
"""

from __future__ import annotations

from . import editing, structure
from .commands import (
    AddParameter,
    AddSection,
    Command,
    CommandResult,
    CreateDocument,
    Preview,
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
        if not structure.can_rename(command.path):
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
