"""Parameter list (middle panel): direct parameters of the selected object.

The pane also hosts the section-scoped "+ Add parameter" entry point: a
header button, enabled only when a document is loaded and an object is
selected, that opens :class:`~.add_parameter_popup.AddParameterPopup`
anchored underneath it. This is deliberately the only add-parameter surface;
creation is never offered by a row's right-click.

A row's right-click context menu instead offers actions on that *existing*
row -- currently just "Remove parameter", also reachable via the Delete key
once a row is current. Context menus never create; creation controls are
never hidden behind a right-click (see the parameter-list pane section of
docs/02-ui.md).
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.tree_model import TreeNode

from .add_parameter_popup import AddParameterPopup


class _ParameterListView(QListWidget):
    """A ``QListWidget`` whose Delete key removes the current row.

    A small subclass -- matching the local key-handling convention already
    used by :class:`~.add_parameter_popup._PopupInput` -- rather than a
    ``QAction`` shortcut. A ``QAction``'s live keyboard binding only fires
    while the widget genuinely holds Qt's application focus, which makes it
    unreliable to drive deterministically; overriding the key event handles
    Delete directly and always acts on whichever row is current, exactly
    like Enter/Escape on the editor cards. This is therefore the *only*
    Delete binding -- the context-menu action deliberately declares none.
    """

    delete_requested = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete:
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)


class ParameterListPanel(QWidget):
    """Lists a node's parameters; emits the selected parameter's path."""

    parameter_selected = Signal(tuple)
    add_parameter_requested = Signal(tuple, str)  # (section_path, typed_alias)
    remove_parameter_requested = Signal(tuple)  # parameter_path

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._node: TreeNode | None = None
        self._model: str | None = None

        self._add_button = QPushButton("+ Add parameter")
        self._add_button.setObjectName("AddParameterButton")
        self._add_button.setEnabled(False)
        self._add_button.setMinimumHeight(28)
        self._add_button.clicked.connect(self._open_add_popup)

        button_container = QWidget()
        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(8, 8, 8, 8)
        button_layout.addWidget(self._add_button)
        layout.addWidget(button_container)

        self._list = _ParameterListView()
        self._list.setObjectName("ParameterListView")
        self._list.itemClicked.connect(self._on_clicked)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu_requested)
        self._list.delete_requested.connect(self._remove_current_parameter)
        layout.addWidget(self._list)

        # The single action behind the context menu's "Remove parameter"
        # entry. It carries no ``QKeySequence``: the live Delete accelerator
        # is ``_ParameterListView.keyPressEvent`` above, so a shortcut here
        # would be a second, redundant binding whose only effect is to print
        # a hint beside the label. Both paths land on the same
        # ``_remove_current_parameter`` handler.
        self._remove_action = QAction("Remove parameter", self)
        self._remove_action.triggered.connect(self._remove_current_parameter)

        self._popup = AddParameterPopup(self)
        self._popup.custom_parameter_requested.connect(self._on_custom_parameter_requested)

    def show_node(self, node: TreeNode | None, model: str | None = None) -> None:
        self._node = node
        self._model = model
        self._add_button.setEnabled(node is not None)
        self._list.clear()
        if node is None:
            return
        for parameter in node.parameters:
            marker = "  ⚠" if parameter.has_errors else ""
            item = QListWidgetItem(f"{parameter.label}{marker}")
            item.setData(256, parameter.path)
            self._list.addItem(item)

    def reveal(
        self,
        node: TreeNode | None,
        parameter_path: tuple[str, ...] | None,
        model: str | None = None,
    ) -> None:
        """Show *node*'s parameters and select/scroll to *parameter_path*.

        This is the parameter list's part of a navigation reveal; it re-lists
        the target object's parameters and highlights the target row when the
        navigation is parameter-level. *model* is the document's declared
        model, needed (alongside the section path) to look up BPX-alias
        suggestions for the add-parameter popup.
        """
        self.show_node(node, model)
        if parameter_path is None:
            return
        target = tuple(parameter_path)
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(256) == target:
                self._list.setCurrentRow(row)
                self._list.scrollToItem(item)
                return

    def _on_clicked(self, item: QListWidgetItem) -> None:
        self.parameter_selected.emit(item.data(256))

    def _on_context_menu_requested(self, pos: QPoint) -> None:
        """Show "Remove parameter" for the row under *pos*, or nothing.

        A right-click always acts on whatever row it lands on -- never a
        stale prior selection -- so the target row is made current first,
        which is also what visibly shows it as the menu's target. Empty
        space -- including an empty list, or no object/document loaded at
        all -- has no row under the cursor, so this opens no menu; a
        disabled menu is not shown either, matching the app's "no disabled
        placeholders" convention.
        """
        item = self._list.itemAt(pos)
        if item is None:
            return
        self._list.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction(self._remove_action)
        menu.exec(self._list.mapToGlobal(pos))

    def _remove_current_parameter(self) -> None:
        """Request removal of whichever row is current.

        The context menu action and the Delete-key accelerator both land
        here; a no-op when nothing is current (e.g. Delete pressed with an
        empty list).
        """
        item = self._list.currentItem()
        if item is None:
            return
        self.remove_parameter_requested.emit(item.data(256))

    def _open_add_popup(self) -> None:
        if self._node is None:
            return
        existing = {parameter.label for parameter in self._node.parameters}
        self._popup.open_for_section(
            self._add_button,
            self._node.label,
            existing,
            self._node.path,
            self._model,
        )

    def _on_custom_parameter_requested(self, typed_alias: str) -> None:
        if self._node is None:
            return
        self.add_parameter_requested.emit(self._node.path, typed_alias)
