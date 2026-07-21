"""ParameterCard: self-contained composition of one parameter's work surface.

Top to bottom, a ``ParameterCard`` holds:

  1. a header (title label + validity badge + ( i ) information button that
     toggles a :class:`~ui_qt.parameter_info_popover.ParameterInfoPopover` -
     the quick glance; the long-form prose lives in the Inspector's
     Documentation tab),
  2. the per-kind value editor, produced by :func:`create_card`,
  3. the parameter's summary description, when present.

``ParameterCard`` is a pure composition container. It forwards the inner
editor's ``draft_changed`` / ``draft_reset`` / ``commit_requested`` signals
unchanged and re-exposes ``parameter``, ``value()``, ``reset()`` and
``is_dirty`` so callers can treat it like the editor it wraps. It does not
decide validity: the badge is driven externally via :meth:`set_validity`, and
all validation orchestration stays in ``InspectorPanel``.

For a parameter whose own key is renamable (``core.structure.can_rename_parameter``
-- User-defined content, Particle materials, Validation runs, or any
parameter leaf the schema defines nowhere, wherever it lives), the header
also carries a small "✎" button that expands an inline Name/Unit row in
place (Concept A of
the completion-track rename/duplicate/move phase). This is the single rename
surface for such a parameter: the parameter-list row's "Rename…" context-menu
action opens/focuses the very same row via :meth:`open_rename_editor`, rather
than a second popup-based implementation. Applying composes the new key and
emits ``rename_requested``; ``InspectorPanel`` executes the ``RenameKey``
command and reports a refusal back via :meth:`show_rename_error`, the same
inline-error convention other cards use for a blocked commit.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import structure
from core.bpx_gateway import FieldMeta
from core.parameter_metadata import resolve_parameter_metadata
from core.parameter_types import split_name_and_unit
from core.tree_model import ParameterItem

from ..icons import PENCIL, hover_icon
from ..latex import symbol_label
from ..parameter_info_popover import ParameterInfoPopover
from ..style import ERROR, MUTED
from .registry import create_card


class ParameterCard(QWidget):
    """Composes the header, per-kind editor and description for one parameter."""

    draft_changed = Signal()
    draft_reset = Signal()
    commit_requested = Signal()
    expand_toggled = Signal(bool)
    bulk_commit_requested = Signal(object)
    #: (path, new_key) -- the inline rename row's "Apply". Only ever emitted
    #: when the pencil button exists at all (``self._renamable``).
    rename_requested = Signal(tuple, str)

    def __init__(self, parameter: ParameterItem, meta: FieldMeta | None) -> None:
        super().__init__()
        self.parameter = parameter
        self._meta = meta
        self._popover: ParameterInfoPopover | None = None
        self._renamable = structure.can_rename_parameter(parameter.path, parameter.value)
        # Resolved once and reused by the ( i ) popover: the symbol shown in the
        # header comes from the same source, so both render identical maths and
        # neither invents anything the dataset does not carry.
        self._metadata = resolve_parameter_metadata(parameter.path, meta)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self._title = QLabel(parameter.label)
        self._title.setObjectName("CardTitle")
        header.addWidget(self._title)
        # The parameter's symbol, as rendered maths, sits beside its name -- the
        # glance the modeller reads by ("Electrode area [m2]", A). Present only
        # for parameters the technical-descriptions dataset documents; every
        # other parameter simply shows no symbol (see resolve_parameter_metadata).
        if self._metadata.symbol:
            symbol = symbol_label(self._metadata.symbol, point_size=13.0, color=MUTED)
            symbol.setObjectName("CardSymbol")
            header.addWidget(symbol)
        if self._renamable:
            # Flat, box-less pencil (Concept A "without the box"): no border or
            # fill of its own, the icon just darkens on hover. A real drawn glyph
            # in the app's icon family, not the bare "✎" text it replaces.
            self._rename_button = QPushButton()
            self._rename_button.setObjectName("CardRenameButton")
            self._rename_button.setToolTip("Rename name & unit")
            self._rename_button.setIcon(hover_icon(PENCIL, 16))
            self._rename_button.setIconSize(QSize(16, 16))
            self._rename_button.setFixedSize(22, 22)
            self._rename_button.setFlat(True)
            self._rename_button.setCursor(Qt.PointingHandCursor)
            self._rename_button.setStyleSheet("border: none; background: transparent; padding: 0;")
            self._rename_button.clicked.connect(self._open_rename_row)
            header.addWidget(self._rename_button)
        else:
            self._rename_button = None
        header.addStretch(1)
        self._badge = QLabel("")
        header.addWidget(self._badge)
        self._info_button = QPushButton("i")
        self._info_button.setObjectName("InfoButton")
        self._info_button.setToolTip("Parameter information")
        self._info_button.setFixedSize(20, 20)
        self._info_button.setStyleSheet(
            "border-radius: 10px; font-style: italic; font-weight: 600;"
        )
        self._info_button.clicked.connect(self._toggle_info_popover)
        header.addWidget(self._info_button)
        layout.addLayout(header)

        if self._renamable:
            self._rename_row = self._build_rename_row()
            layout.addWidget(self._rename_row)
        else:
            self._rename_row = None

        self._editor = create_card(parameter, meta)
        self._editor.draft_changed.connect(self.draft_changed)
        self._editor.draft_reset.connect(self.draft_reset)
        self._editor.commit_requested.connect(self.commit_requested)
        self._editor.expand_toggled.connect(self.expand_toggled)
        self._editor.expand_toggled.connect(self._on_expand_toggled)
        self._editor.bulk_commit_requested.connect(self.bulk_commit_requested)
        # Value row: the editor plus a trailing slot. The trailing slot is
        # reserved -- not built -- for a future Reference document's value
        # and delta once multi-document lands (docs/05-future.md); no
        # widget or API for it exists yet, so today's layout is visually
        # identical to the editor sitting alone.
        value_row = QHBoxLayout()
        value_row.addWidget(self._editor, 1)
        layout.addLayout(value_row)

        # Description: quiet muted prose under the editor -- not a boxed text
        # widget, which read as another input and claimed a fixed slab of
        # height whatever its one sentence needed. Selectable so it can still
        # be copied. Hidden while the editor's grid takes over the pane (a big
        # table needs the room; the live preview chart above the grid stays).
        self._description_widgets: list[QWidget] = []
        if parameter.description:
            desc = QLabel(parameter.description)
            desc.setObjectName("CardDescription")
            desc.setWordWrap(True)
            desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(desc)
            self._description_widgets = [desc]

    def _on_expand_toggled(self, expanded: bool) -> None:
        """Hide the description while the grid is expanded, restore on collapse."""
        for widget in self._description_widgets:
            widget.setVisible(not expanded)

    def value(self) -> object:
        """Return the inner editor's current draft value in raw-dict form."""
        return self._editor.value()

    def reset(self) -> None:
        """Restore the inner editor to the original (last committed) value."""
        self._editor.reset()

    @property
    def is_editable(self) -> bool:
        return self._editor.is_editable

    @property
    def is_dirty(self) -> bool:
        """Whether the inner editor's draft differs from its original value."""
        return self._editor.is_dirty

    def commit_blocked_reason(self) -> str | None:
        """Why the inner editor's draft has no representation, if it has none."""
        return self._editor.commit_blocked_reason()

    def set_cell_issues(self, issues) -> None:
        """Pass the validator's per-cell diagnostics to the inner editor."""
        self._editor.set_cell_issues(issues)

    def set_validity(self, text: str, colour: str) -> None:
        """Drive the header badge; validity decisions stay in the Inspector."""
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"color: white; background: {colour}; padding: 2px 8px; border-radius: 3px;"
        )

    def _toggle_info_popover(self) -> None:
        """Open the info popover on the first click, close it on the second."""
        if self._popover is not None and self._popover.isVisible():
            self._popover.hide()
            return
        if self._popover is None:
            self._popover = ParameterInfoPopover(self)
        self._popover.show_metadata(self._metadata)
        self._popover.open_below(self._info_button)

    # ------------------------------------------------------------------
    # Inline rename row (Concept A) -- only built when ``self._renamable``
    # ------------------------------------------------------------------

    def _build_rename_row(self) -> QWidget:
        """Build (but do not populate) the collapsible Name/Unit/Apply row."""
        self._rename_name = QLineEdit()
        self._rename_name.setObjectName("AddParameterInput")  # shared popup styling
        self._rename_name.setPlaceholderText("Name")
        self._rename_name.textChanged.connect(self._update_rename_apply_enabled)

        self._rename_unit = QLineEdit()
        self._rename_unit.setObjectName("AddParameterInput")
        self._rename_unit.setPlaceholderText("Unit (optional)")

        self._rename_apply = QPushButton("Apply")
        self._rename_apply.setEnabled(False)
        self._rename_apply.clicked.connect(self._apply_rename)

        self._rename_cancel = QPushButton("Cancel")
        self._rename_cancel.clicked.connect(self._collapse_rename_row)

        fields = QHBoxLayout()
        fields.setContentsMargins(0, 0, 0, 0)
        fields.addWidget(self._rename_name, 2)
        fields.addWidget(self._rename_unit, 1)
        fields.addWidget(self._rename_apply)
        fields.addWidget(self._rename_cancel)

        self._rename_error = QLabel("")
        self._rename_error.setObjectName("CardRenameError")
        self._rename_error.setStyleSheet(f"color: {ERROR};")
        self._rename_error.setWordWrap(True)
        self._rename_error.hide()

        row = QWidget()
        row.setObjectName("CardRenameRow")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 4, 0, 4)
        row_layout.setSpacing(4)
        row_layout.addLayout(fields)
        row_layout.addWidget(self._rename_error)
        row.hide()
        return row

    def open_rename_editor(self) -> None:
        """Expand (or refocus) the inline rename row.

        The single entry point both the pencil button and the parameter-list
        row's "Rename…" context-menu action drive -- one rename surface, not
        two independent implementations. A no-op for a non-renamable card
        (``self._rename_row`` is ``None``).
        """
        self._open_rename_row()

    def show_rename_error(self, message: str) -> None:
        """Show *message* inline under the (still-expanded) rename row.

        Called by ``InspectorPanel`` when the ``RenameKey`` command refuses
        the composed name (empty, unchanged, or already taken by a sibling)
        -- the same inline-error convention other cards use for a blocked
        commit, rather than a dialog. The user's typed values are left
        untouched so they can correct and retry.
        """
        if self._rename_row is None:
            return
        self._rename_row.show()
        self._rename_error.setText(message)
        self._rename_error.show()

    def _open_rename_row(self, *_args) -> None:
        if self._rename_row is None:
            return
        name, unit = split_name_and_unit(self.parameter.label)
        self._rename_name.setText(name)
        self._rename_unit.setText(unit)
        self._rename_error.hide()
        self._rename_error.setText("")
        self._update_rename_apply_enabled()
        self._rename_row.show()
        self._rename_name.setFocus()
        self._rename_name.selectAll()

    def _collapse_rename_row(self, *_args) -> None:
        if self._rename_row is None:
            return
        self._rename_row.hide()
        self._rename_error.hide()
        self._rename_error.setText("")

    def _update_rename_apply_enabled(self, *_args) -> None:
        self._rename_apply.setEnabled(bool(self._rename_name.text().strip()))

    def _apply_rename(self) -> None:
        name = self._rename_name.text().strip()
        if not name:
            return
        unit = self._rename_unit.text().strip()
        new_key = f"{name} [{unit}]" if unit else name
        self.rename_requested.emit(self.parameter.path, new_key)
