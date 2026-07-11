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


def set_values(
    raw: dict, updates: tuple[tuple[tuple[str, ...], object], ...]
) -> dict:
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


def add_section(raw: dict, parent_path: tuple[str, ...], key: str) -> dict:
    """Return a copy of ``raw`` with an empty object ``key`` under the parent."""
    return add_parameter(raw, parent_path, key, {})


def remove_section(raw: dict, path: tuple[str, ...]) -> dict:
    """Return a copy of ``raw`` with the object at ``path`` removed."""
    return remove_parameter(raw, path)
