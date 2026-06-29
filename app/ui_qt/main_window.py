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
        bar.addAction("Export", self._save)
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
        self._state.select(path)
        self._params.show_node(self._state.selected_node())
        self._inspector.show_placeholder()

    def _select_parameter(self, path: tuple) -> None:
        self._state.select_parameter(path)
        parameter = self._state.selected_parameter()
        if parameter is not None:
            self._inspector.show_parameter(parameter)

    def _jump_to_path(self, path: tuple) -> None:
        if not path:
            return
        self._select_node(tuple(path[:-1]))
        self._select_parameter(tuple(path))

    def _on_committed(self) -> None:
        kept_node = self._state.selected_path
        kept_param = self._state.selected_parameter_path
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
            self._state.load(Path(name).read_bytes(), Path(name).name)
        except LoadError as exc:
            QMessageBox.critical(self, "Cannot open file", str(exc))
            return
        self._refresh_all()

    def _save(self) -> None:
        if not self._state.has_document:
            return
        document = self._state.document
        name, _ = QFileDialog.getSaveFileName(self, "Save BPX", document.filename, "BPX (*.json *.yaml *.yml)")
        if not name:
            return
        fmt = "yaml" if name.lower().endswith((".yml", ".yaml")) else "json"
        Path(name).write_bytes(export.to_bytes(document.raw, fmt))

    def _refresh_all(self) -> None:
        document = self._state.document
        if document is not None:
            self._tree.set_root(document.tree)
        self._params.show_node(None)
        self._inspector.show_placeholder()
        self._validation.refresh(document)
        self._search.index_document(document)
        count = (document.error_count + document.warning_count) if document else 0
        self._tabs.setTabText(1, f"Validation ({count})")
