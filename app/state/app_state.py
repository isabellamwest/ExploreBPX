"""Application state container (frontend-agnostic).

Holds the currently open document, the selected object-node path, and the
selected parameter path (when a single parameter is being inspected in detail).
It contains no UI-framework code so it can be reused by any frontend. The UI
layer is responsible for persisting a single instance (e.g. in Streamlit session
state).
"""

from __future__ import annotations

from dataclasses import dataclass

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

    @property
    def has_document(self) -> bool:
        return self.document is not None

    def load(self, data: bytes | str, filename: str) -> None:
        """Open a file, replacing any current document and selection."""
        self.document = BPXDocument.from_bytes(data, filename)
        self.selected_path = None
        self.selected_parameter_path = None

    def clear(self) -> None:
        self.document = None
        self.selected_path = None
        self.selected_parameter_path = None

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
