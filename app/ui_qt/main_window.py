"""Main application window: toolbar, Editor/Validation tabs, three panels.

This is wiring only: it owns the single :class:`AppState`, connects panel
signals to state mutations, and refreshes views. No BPX logic lives here.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QWidget,
)

from core import export
from core.bpx_gateway import BPX_VERSION, LoadError
from state.app_state import AppState

from .inspector import InspectorPanel
from .parameter_list import ParameterListPanel
from .search import SearchBar
from .style import STYLESHEET
from .tree_panel import TreePanel
from .validation_panel import ValidationPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ExploreBPX")
        self.setStyleSheet(STYLESHEET)
        self.resize(1200, 760)
        self._state = AppState()

        self._tree = TreePanel()
        self._params = ParameterListPanel()
        self._inspector = InspectorPanel(self._state)
        self._validation = ValidationPanel()
        self._search = SearchBar()

        self._build_toolbar()
        self._build_central()
        self._connect()
        self._refresh_all()

    def _build_toolbar(self) -> None:
        bar = self.addToolBar("Main")
        bar.addAction("Open", self._open)
        new = bar.addAction("New")
        new.setEnabled(False)
        bar.addAction("Save", self._save)
        bar.addAction("Export", self._export)
        compare = bar.addAction("Compare")
        compare.setEnabled(False)
        bar.addSeparator()
        bar.addWidget(self._search)

    def _build_central(self) -> None:
        splitter = QSplitter()
        for panel in (self._tree, self._params, self._inspector):
            panel.setObjectName("Panel")
            splitter.addWidget(panel)
        splitter.setSizes([240, 280, 680])

        self._tabs = QTabWidget()
        self._tabs.addTab(splitter, "Editor")
        self._tabs.addTab(self._validation, "Validation")
        self.setCentralWidget(self._tabs)

    def _connect(self) -> None:
        self._tree.node_selected.connect(self._select_node)
        self._params.parameter_selected.connect(self._select_parameter)
        self._inspector.committed.connect(self._on_committed)
        self._validation.issue_activated.connect(self._jump_to_path)
        self._search.parameter_chosen.connect(self._jump_to_path)

    # --- navigation -----------------------------------------------------
    def _select_node(self, path: tuple) -> None:
        if self._state.active is None:
            return
        self._state.active.select(path)
        self._params.show_node(self._state.active.selected_node())
        self._inspector.show_placeholder()

    def _select_parameter(self, path: tuple) -> None:
        if self._state.active is None:
            return
        self._state.active.select_parameter(path)
        parameter = self._state.active.selected_parameter()
        if parameter is not None:
            self._inspector.show_parameter(parameter)

    def _jump_to_path(self, path: tuple) -> None:
        if not path or self._state.active is None:
            return
        self._select_node(tuple(path[:-1]))
        self._select_parameter(tuple(path))

    def _on_committed(self) -> None:
        if self._state.active is None:
            return
        kept_node = self._state.active.selected_path
        kept_param = self._state.active.selected_parameter_path
        self._refresh_all()
        if kept_node:
            self._select_node(kept_node)
        if kept_param:
            self._select_parameter(kept_param)

    # --- file actions ---------------------------------------------------
    def _open(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Open BPX", "", "BPX (*.json *.yaml *.yml)")
        if not name:
            return
        try:
            self._state.open(Path(name))
        except (LoadError, OSError) as exc:
            QMessageBox.critical(self, "Cannot open file", str(exc))
            return
        self._refresh_all()

    def _save(self) -> None:
        """Write the document to its backing file.

        If no backing file is set (unsaved new document), a Save As dialog
        is shown first. Does not affect export copies.
        """
        if self._state.active is None:
            return
        session = self._state.active
        if session.backing_file is None:
            name, _ = QFileDialog.getSaveFileName(
                self, "Save BPX",
                session.document.filename if session.document else "",
                "BPX (*.json *.yaml *.yml)",
            )
            if not name:
                return
            session.backing_file = Path(name)
        try:
            session.save()
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self._update_title()

    def _export(self) -> None:
        """Write a copy of the document to a user-chosen location.

        Does not affect the backing file or dirty state.
        """
        if self._state.active is None or self._state.active.document is None:
            return
        session = self._state.active
        default = str(session.backing_file) if session.backing_file else session.document.filename
        name, _ = QFileDialog.getSaveFileName(
            self, "Export BPX", default, "BPX (*.json *.yaml *.yml)"
        )
        if not name:
            return
        fmt = "yaml" if name.lower().endswith((".yml", ".yaml")) else "json"
        try:
            Path(name).write_bytes(export.to_bytes(session.document.raw, fmt))
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _update_title(self) -> None:
        """Sync the window title with the active session's name and dirty state."""
        session = self._state.active
        if session is None or session.document is None:
            self.setWindowTitle("ExploreBPX")
            return
        name = session.backing_file.name if session.backing_file else session.document.filename
        prefix = "* " if session.dirty else ""
        self.setWindowTitle(f"{prefix}{name} \u2014 ExploreBPX")

    def _refresh_all(self) -> None:
        document = self._state.active.document if self._state.active else None
        if document is not None:
            self._tree.set_root(document.tree)
        self._params.show_node(None)
        self._inspector.show_placeholder()
        self._validation.refresh(document)
        self._search.index_document(document)
        count = (document.error_count + document.warning_count) if document else 0
        self._tabs.setTabText(1, f"Validation ({count})")
        self._update_title()
