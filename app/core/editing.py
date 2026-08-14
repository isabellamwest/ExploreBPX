"""Pure editing operations on a raw BPX dictionary (frontend-agnostic).

The raw dict is the document's single source of truth (see
:mod:`core.document`). These helpers take a raw dict plus an alias path and
return a **new** dict with the edit applied, leaving the input untouched. They
contain no UI and no BPX-package coupling, so they are fully unit-testable and
reusable by any frontend.

Validation is intentionally *not* performed here: callers re-validate the
returned dict through :mod:`core.bpx_gateway`, keeping a single validation
authority (the official ``bpx`` package).
"""

from __future__ import annotations

import copy

from . import parameter_types


class EditError(KeyError):
    """Raised when an edit path does not resolve in the raw dict."""


def _navigate(raw: dict, path: tuple[str, ...]) -> dict:
    """Return the parent dict that directly owns ``path[-1]``.

    Raises :class:`EditError` if any intermediate segment is missing or is not
    a dictionary.
    """
    node: object = raw
    for key in path[:-1]:
        if not isinstance(node, dict) or key not in node:
            raise EditError(f"Path segment not found: {key!r} in {path!r}")
        node = node[key]
    if not isinstance(node, dict):
        raise EditError(f"Parent of {path[-1]!r} is not an object")
    return node


def set_value(raw: dict, path: tuple[str, ...], value: object) -> dict:
    """Return a copy of ``raw`` with the leaf at ``path`` set to ``value``."""
    if not path:
        raise EditError("Cannot set a value at the document root")
    updated = copy.deepcopy(raw)
    parent = _navigate(updated, path)
    parent[path[-1]] = value
    return updated


def set_values(raw: dict, updates: tuple[tuple[tuple[str, ...], object], ...]) -> dict:
    """Return a copy of ``raw`` with every ``(path, value)`` in *updates* applied.

    All-or-nothing: the writes go into a single copy, so if any path fails to
    resolve the :class:`EditError` propagates before the copy is returned and
    the caller's dict is never half-updated. One deep copy for the whole batch,
    not one per write -- a CSV import touching four multi-thousand-row arrays
    should not copy the document four times.
    """
    if not updates:
        raise EditError("No updates to apply")
    updated = copy.deepcopy(raw)
    for path, value in updates:
        if not path:
            raise EditError("Cannot set a value at the document root")
        parent = _navigate(updated, path)
        parent[path[-1]] = value
    return updated


def add_parameter(raw: dict, parent_path: tuple[str, ...], key: str, value: object) -> dict:
    """Return a copy of ``raw`` with ``key`` added under ``parent_path``."""
    updated = copy.deepcopy(raw)
    parent = _navigate(updated, parent_path + (key,))
    parent[key] = value
    return updated


def remove_parameter(raw: dict, path: tuple[str, ...]) -> dict:
    """Return a copy of ``raw`` with the parameter at ``path`` removed."""
    if not path:
        raise EditError("Cannot remove the document root")
    updated = copy.deepcopy(raw)
    parent = _navigate(updated, path)
    parent.pop(path[-1], None)
    return updated


def rename_key(raw: dict, path: tuple[str, ...], new_key: str) -> dict:
    """Return a copy of ``raw`` with the key at ``path`` renamed to ``new_key``.

    The key keeps its **position** in the owning dict -- the raw dict's key
    order is what exports, so a rename must not shuffle the renamed section to
    the end of the file. The value moves untouched, descendants and all.

    Raises :class:`EditError` when the key is missing or when ``new_key``
    already exists in the parent (overwriting a sibling would silently destroy
    its contents -- a rename is a move, never a merge).
    """
    if not path:
        raise EditError("Cannot rename the document root")
    updated = copy.deepcopy(raw)
    parent = _navigate(updated, path)
    old_key = path[-1]
    if old_key not in parent:
        raise EditError(f"Path segment not found: {old_key!r} in {path!r}")
    if new_key != old_key and new_key in parent:
        raise EditError(f"Key already exists: {new_key!r}")
    items = [(new_key if key == old_key else key, value) for key, value in parent.items()]
    parent.clear()
    parent.update(items)
    return updated


def move_key(raw: dict, path: tuple[str, ...], direction: str) -> dict:
    """Return a copy of ``raw`` with the key at ``path`` moved one position
    up or down among its siblings within the owning dict.

    ``direction`` is ``"up"`` or ``"down"``. Like :func:`rename_key`, this is
    a dict-rebuild that swaps the two neighbouring entries -- the value moves
    untouched, descendants and all.

    Raises :class:`EditError` when the key is missing, when ``direction`` is
    neither ``"up"`` nor ``"down"``, or when the move would go past the
    first/last sibling (a boundary move).
    """
    if not path:
        raise EditError("Cannot move the document root")
    if direction not in ("up", "down"):
        raise EditError(f"Unknown move direction: {direction!r}")
    updated = copy.deepcopy(raw)
    parent = _navigate(updated, path)
    key = path[-1]
    if key not in parent:
        raise EditError(f"Path segment not found: {key!r} in {path!r}")
    keys = list(parent)
    index = keys.index(key)
    new_index = index - 1 if direction == "up" else index + 1
    if not (0 <= new_index < len(keys)):
        raise EditError(f"Cannot move {key!r} further {direction}")
    keys[index], keys[new_index] = keys[new_index], keys[index]
    items = [(k, parent[k]) for k in keys]
    parent.clear()
    parent.update(items)
    return updated


def _next_duplicate_name(key: str, existing_keys: object) -> str:
    """The first unique sibling name for a duplicate of ``key``.

    A numeric suffix is inserted before any unit bracket -- ``"Foo"`` ->
    ``"Foo (2)"``, ``"Foo [V]"`` -> ``"Foo (2) [V]"`` -- incrementing until
    the candidate is not already among ``existing_keys``.
    """
    name, unit = parameter_types.split_name_and_unit(key)
    existing = set(existing_keys)
    suffix = 2
    while True:
        candidate = f"{name} ({suffix})" + (f" [{unit}]" if unit else "")
        if candidate not in existing:
            return candidate
        suffix += 1


def duplicate_key(raw: dict, path: tuple[str, ...]) -> tuple[dict, str]:
    """Return a copy of ``raw`` with the value at ``path`` deep-copied into a
    new sibling key immediately after the original, plus the new key.

    The new key is named by :func:`_next_duplicate_name`. Unlike
    :func:`add_parameter` (which always lands at whatever position dict
    insertion gives it), the duplicate is spliced in right after its source
    so it reads as "the copy of that entry", not as an unrelated addition at
    the end.

    Raises :class:`EditError` when the key is missing.
    """
    if not path:
        raise EditError("Cannot duplicate the document root")
    updated = copy.deepcopy(raw)
    parent = _navigate(updated, path)
    key = path[-1]
    if key not in parent:
        raise EditError(f"Path segment not found: {key!r} in {path!r}")
    new_key = _next_duplicate_name(key, parent.keys())
    items: list[tuple[str, object]] = []
    for existing_key, value in parent.items():
        items.append((existing_key, value))
        if existing_key == key:
            items.append((new_key, copy.deepcopy(value)))
    parent.clear()
    parent.update(items)
    return updated, new_key


def add_section(raw: dict, parent_path: tuple[str, ...], key: str) -> dict:
    """Return a copy of ``raw`` with an empty object ``key`` under the parent."""
    return add_parameter(raw, parent_path, key, {})


def remove_section(raw: dict, path: tuple[str, ...]) -> dict:
    """Return a copy of ``raw`` with the object at ``path`` removed."""
    return remove_parameter(raw, path)
