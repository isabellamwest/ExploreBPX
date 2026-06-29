"""Global parameter search: jump to any parameter by name across the file."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCompleter, QLineEdit

from core.document import BPXDocument


class SearchBar(QLineEdit):
    """A search box that completes parameter paths and jumps on selection."""

    parameter_chosen = Signal(tuple)

    def __init__(self) -> None:
        super().__init__()
        self.setPlaceholderText("Search parameters…")
        self._paths: dict[str, tuple[str, ...]] = {}
        self._completer = QCompleter([])
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.activated.connect(self._on_activated)
        self.setCompleter(self._completer)

    def index_document(self, document: BPXDocument | None) -> None:
        self._paths.clear()
        if document is not None:
            for path in document._parameter_path_map:  # noqa: SLF001 - read-only index
                self._paths[" → ".join(path)] = path
        self._completer.model().setStringList(sorted(self._paths))

    def _on_activated(self, text: str) -> None:
        path = self._paths.get(text)
        if path is not None:
            self.parameter_chosen.emit(path)
            self.clear()
