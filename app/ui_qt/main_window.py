"""Main application window: activity bar, workspace stack, issues drawer.

This is wiring only: it owns the single :class:`AppState`, connects panel
signals to state mutations, and refreshes views. No BPX logic lives here.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from core import export
from core.bpx_gateway import BPX_VERSION, LoadError
from state.app_state import AppState

from .activity_bar import ActivityBar
from .inspector import InspectorPanel
from .issues_drawer import IssuesDrawer
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
        self._activity_bar = ActivityBar()
        self._issues_drawer = IssuesDrawer()
        self._status_label = QLabel()

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._connect()
        self._refresh_all()

    def _build_toolbar(self) -> None:
        bar = self.addToolBar("Main")
        bar.addAction("Open", self._open)
        bar.addAction("Save", self._save)
        bar.addAction("Export", self._export)
        bar.addSeparator()
        bar.addWidget(self._search)

    def _build_central(self) -> None:
        # Editor view: three-panel splitter.
        editor_splitter = QSplitter()
        for panel in (self._tree, self._params, self._inspector):
            panel.setObjectName("Panel")
            editor_splitter.addWidget(panel)
        editor_splitter.setSizes([240, 280, 680])

        # Workspace stack: page 0 = editor, page 1 = validation.
        self._stack = QStackedWidget()
        self._stack.addWidget(editor_splitter)   # page 0
        self._stack.addWidget(self._validation)  # page 1

        # Register activity bar entries (order must match stack pages).
        self._btn_editor = self._activity_bar.add_view("Editor", page_index=0, checked=True)
        self._btn_validation = self._activity_bar.add_view("Validation", page_index=1)

        # Assemble the central layout.
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._activity_bar)
        layout.addWidget(self._stack, 1)
        layout.addWidget(self._issues_drawer)
        self.setCentralWidget(central)

    def _build_statusbar(self) -> None:
        bar = QStatusBar()
        bar.addPermanentWidget(self._status_label, 1)
        self.setStatusBar(bar)

    def _connect(self) -> None:
        self._tree.node_selected.connect(self._select_node)
        self._params.parameter_selected.connect(self._select_parameter)
        self._inspector.committed.connect(self._on_committed)
        self._validation.issue_activated.connect(self._jump_to_path)
        self._issues_drawer.issue_activated.connect(self._jump_to_path)
        self._search.parameter_chosen.connect(self._jump_to_path)
        self._activity_bar.view_requested.connect(self._on_view_changed)

    # --- navigation -----------------------------------------------------
    def _on_view_changed(self, page_index: int) -> None:
        """Switch the workspace and hide the Issues drawer outside the editor."""
        self._stack.setCurrentIndex(page_index)
        # The drawer is parameter-card context; hide it when leaving the editor.
        # Visibility within the editor is governed by _select_parameter.
        if page_index != 0:
            self._issues_drawer.setVisible(False)

    def _select_node(self, path: tuple) -> None:
        if self._state.active is None:
            return
        self._state.active.select(path)
        self._params.show_node(self._state.active.selected_node())
        self._inspector.show_placeholder()
        self._issues_drawer.show_parameter(None)
        self._issues_drawer.setVisible(False)

    def _select_parameter(self, path: tuple) -> None:
        if self._state.active is None:
            return
        self._state.active.select_parameter(path)
        parameter = self._state.active.selected_parameter()
        if parameter is not None:
            self._inspector.show_parameter(parameter)
        self._issues_drawer.show_parameter(parameter)
        self._issues_drawer.setVisible(parameter is not None)

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
        self._issues_drawer.reset()
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
        """Sync the window title and status bar with the active session state."""
        session = self._state.active
        if session is None or session.document is None:
            self.setWindowTitle("ExploreBPX")
            self._status_label.setText("")
            return
        name = session.backing_file.name if session.backing_file else session.document.filename
        prefix = "* " if session.dirty else ""
        self.setWindowTitle(f"{prefix}{name} \u2014 ExploreBPX")
        state_text = "Modified" if session.dirty else "Saved"
        self._status_label.setText(f"{name}  |  {state_text}")

    def _refresh_all(self) -> None:
        document = self._state.active.document if self._state.active else None
        if document is not None:
            self._tree.set_root(document.tree)
        self._params.show_node(None)
        self._inspector.show_placeholder()
        self._validation.refresh(document)
        self._issues_drawer.show_parameter(None)
        self._issues_drawer.setVisible(False)
        self._search.index_document(document)
        count = (document.error_count + document.warning_count) if document else 0
        self._btn_validation.setText(f"Validation ({count})" if count else "Validation")
        self._update_title()
