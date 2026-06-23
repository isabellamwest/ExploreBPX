"""Application state container (frontend-agnostic).

Holds the currently open document and the selected parameter path. It contains
no UI-framework code so it can be reused by any frontend. The UI layer is
responsible for persisting a single instance (e.g. in Streamlit session state).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.document import BPXDocument
from core.tree_model import TreeNode


@dataclass
class AppState:
    """The full application state for a single open BPX file.

    ``document`` is singular for V1. A future multi-file version can replace it
    with a collection without changing the UI's interaction with this class.
    """

    document: BPXDocument | None = None
    selected_path: tuple[str, ...] | None = None

    @property
    def has_document(self) -> bool:
        return self.document is not None

    def load(self, data: bytes | str, filename: str) -> None:
        """Open a file, replacing any current document and selection."""
        self.document = BPXDocument.from_bytes(data, filename)
        self.selected_path = None

    def clear(self) -> None:
        self.document = None
        self.selected_path = None

    def select(self, path: tuple[str, ...]) -> None:
        self.selected_path = tuple(path)

    def selected_node(self) -> TreeNode | None:
        if self.document is None or self.selected_path is None:
            return None
        return self.document.find(self.selected_path)
