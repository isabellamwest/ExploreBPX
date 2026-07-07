"""The single frontend navigation coordinator.

``NavigationService`` owns navigation *state and requests* only. It resolves a
requested target path against the domain document, updates the navigation
selection on the active :class:`DocumentSession`, and emits one ``navigated``
notification carrying the resolved target identity. It has no knowledge of Qt
widgets and performs no reveal behaviour: subscribing views (tree, parameter
list, Inspector) each reveal their own part of the target.

The service lives in ``ui_qt/`` because it is frontend orchestration; ``state/``
only stores the selected paths. The ``Signal`` is the transport mechanism for
the notification, not coupling to any concrete widget.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from core.tree_model import ParameterItem, TreeNode
from state.app_state import AppState


@dataclass(frozen=True)
class NavigationTarget:
    """The resolved identity of a navigation destination.

    Carries the resolved domain objects so subscribing views reveal without
    re-resolving. ``parameter`` is ``None`` for an object-level target.
    """

    object_path: tuple[str, ...]
    node: TreeNode
    parameter_path: tuple[str, ...] | None = None
    parameter: ParameterItem | None = None


class NavigationService(QObject):
    """Resolve a target path, update selection state, and notify subscribers."""

    navigated = Signal(object)  # emits a NavigationTarget

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def navigate(self, path: tuple[str, ...]) -> None:
        """Resolve *path* best-effort, update state, and emit ``navigated``.

        Exact object and parameter paths (from tree/list clicks) resolve via the
        exact-lookup fast path; partial validation locations fall back to
        suffix matching. Parameters take priority over objects, matching the
        established navigation semantics. No-ops when there is no active
        document or nothing resolves.
        """
        if not path or self._state.active is None:
            return
        document = self._state.active.document
        if document is None:
            return
        key = tuple(path)

        parameter = document.find_best_parameter(key)
        if parameter is not None:
            object_path = tuple(parameter.path[:-1])
            node = document.find_best(object_path) or document.tree
            self._state.active.select(object_path)
            self._state.active.select_parameter(tuple(parameter.path))
            self.navigated.emit(
                NavigationTarget(
                    object_path=object_path,
                    node=node,
                    parameter_path=tuple(parameter.path),
                    parameter=parameter,
                )
            )
            return

        node = document.find_best(key)
        if node is not None:
            self._state.active.select(tuple(node.path))
            self.navigated.emit(
                NavigationTarget(object_path=tuple(node.path), node=node)
            )
