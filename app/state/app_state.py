"""Application-level state container (frontend-agnostic).

AppState owns the single active DocumentSession. It is the entry point for
opening and closing documents from the UI layer. All per-document state
(selection, undo, document reference) lives in DocumentSession.
"""

from __future__ import annotations

from core.document import BPXDocument
from state.document_session import DocumentSession


class AppState:
    """Application-level container for the active document session.

    In the current single-document design, AppState holds one optional
    DocumentSession. Future multi-document support can extend this class to
    hold a collection of sessions without changing how the UI interacts with
    individual sessions.
    """

    def __init__(self) -> None:
        self.active: DocumentSession | None = None

    @property
    def has_document(self) -> bool:
        """True when a document session is open."""
        return self.active is not None

    def open(self, data: bytes | str, filename: str) -> None:
        """Open a file, creating a fresh DocumentSession."""
        document = BPXDocument.from_bytes(data, filename)
        self.active = DocumentSession(document)

    def close(self) -> None:
        """Close the active session."""
        self.active = None
