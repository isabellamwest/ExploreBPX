"""ParameterCard: self-contained composition of one parameter's work surface.

Top to bottom, a ``ParameterCard`` holds:

  1. a header band (title label + validity dot-and-text + ( i ) information
     button that toggles a
     :class:`~ui_qt.parameter_info_popover.ParameterInfoPopover` -
     the quick glance; the long-form prose lives in the Inspector's
     Documentation section),
  2. the parameter's summary description, when present -- always directly
     under the title (and the rename row, when open), in both modes below,
     for consistency: it describes the parameter, not either value,
  3. the per-kind value editor (:func:`create_card`),
  4. the pinned references' values for this parameter
     (:meth:`set_reference_groups`), when any pin has it -- the aligned-rows
     ledger (design rule 3): a "Main" role label joins the editor's own row,
     and one :class:`~.reference_block.ReferenceLedger` row per distinct
     reference value sits below (shared with ``GhostParameterCard``), badge
     clusters in the same fixed-width role column so every value starts at
     the same x, with a quiet "Pull" (or muted "same") after each value.
     The "Main" label and the whole ledger are absent entirely with no
     reference pinned -- the card is then exactly today's, full width.

``ParameterCard`` is a pure composition container. It forwards the inner
editor's ``draft_changed`` / ``draft_reset`` / ``commit_requested`` signals
unchanged and re-exposes ``parameter``, ``value()``, ``reset()`` and
``is_dirty`` so callers can treat it like the editor it wraps. It does not
decide validity: the header's dot-plus-plain-text mark (the same validity
language the Workspace page speaks; the old solid "Valid" pill retired with
it) is driven externally via :meth:`set_validity`, and all validation
orchestration stays in ``InspectorPanel``.

For a parameter whose own key is renamable (``core.structure.can_rename_parameter``
-- User-defined content, Particle materials, Validation runs, or any
parameter leaf the schema defines nowhere, wherever it lives), the header
also carries a small "✎" button that expands an inline Name/Unit row in
place. This is the single rename surface for such a parameter: the
parameter-list row's "Rename…" context-menu
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
from core.compare import ValueGroup, matching_table_rows
from core.parameter_metadata import resolve_parameter_metadata
from core.parameter_types import ParameterKind, classify, split_name_and_unit
from core.tree_model import ParameterItem

from ..icons import DOT, PENCIL, hover_icon, html_img
from ..latex import symbol_label
from ..parameter_info_popover import ParameterInfoPopover
from ..parameter_row import value_preview
from ..reference_identity import ReferencePin
from .. import style, typography
from ..style import ERROR, MUTED
from .bodies import table_rows
from .function import table_is_representable
from .page import page_content, page_header
from .reference_block import LedgerRowSpec, ReferenceLedger
from .registry import create_card

#: Kinds whose main editor shows a unit label (``ScalarCard``/``IntegerCard``
#: read ``parameter.unit`` directly) -- the same kinds whose reference row
#: shows one, mirroring the main row. Every other kind's main editor -- an
#: enum dropdown, a checkbox, a grid, a mode strip -- carries no separate
#: unit affordance, so the reference row shows none either.
_UNIT_LABEL_KINDS = (ParameterKind.SCALAR, ParameterKind.INTEGER)


class ParameterCard(QWidget):
    """Composes the header, per-kind editor and description for one parameter."""

    draft_changed = Signal()
    draft_reset = Signal()
    commit_requested = Signal()
    bulk_commit_requested = Signal(object)
    #: (path, new_key) -- the inline rename row's "Apply". Only ever emitted
    #: when the pencil button exists at all (``self._renamable``).
    rename_requested = Signal(tuple, str)
    #: A ledger row's "Pull", carrying that row's ``ValueGroup``. Forwarded
    #: verbatim from the (lazily built) ledger; ``InspectorPanel`` wires
    #: this to a source-named ``PullParameter`` command.
    pull_requested = Signal(object)

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

        # Structured-page layout: a full-bleed header block (title row,
        # rename row, description) closed by a hairline,
        # then the content column (editor, reference section) on the shared
        # gutter -- see cards/page.py.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header_frame, header_box = page_header()

        header = QHBoxLayout()
        self._title = QLabel(parameter.label)
        self._title.setObjectName("CardTitle")
        header.addWidget(self._title)
        # The parameter's symbol, as rendered maths, sits beside its name -- the
        # glance the modeller reads by ("Electrode area [m2]", A). Present only
        # for parameters the technical-descriptions dataset documents; every
        # other parameter simply shows no symbol (see resolve_parameter_metadata).
        if self._metadata.symbol:
            # The symbol belongs to the title beside it, so it shares its rung.
            symbol = symbol_label(self._metadata.symbol, size=typography.TITLE, color=MUTED)
            symbol.setObjectName("CardSymbol")
            header.addWidget(symbol)
        if self._renamable:
            # Flat, box-less pencil: no border or fill of its own, the icon
            # just darkens on hover. A real drawn glyph
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
        # Validity mark: the shared dot family plus a separate plain text
        # label (the "dot-plus-plain-text language" the Workspace page
        # introduced), not a solid pill -- tests and the driver read the
        # text via ``self._badge.text()``.
        self._dot = QLabel("")
        self._dot.setObjectName("ValidityDot")
        header.addWidget(self._dot)
        self._badge = QLabel("")
        self._badge.setObjectName("CardValidityText")
        header.addWidget(self._badge)
        self._info_button = QPushButton("i")
        self._info_button.setObjectName("InfoButton")
        self._info_button.setToolTip("Parameter information")
        self._info_button.setFixedSize(20, 20)
        self._info_button.setStyleSheet(
            f"border-radius: 10px; font-style: italic; {typography.semibold_qss()}"
        )
        self._info_button.clicked.connect(self._toggle_info_popover)
        header.addWidget(self._info_button)
        header_box.addLayout(header)

        if self._renamable:
            self._rename_row = self._build_rename_row()
            header_box.addWidget(self._rename_row)
        else:
            self._rename_row = None

        # Description: quiet muted prose directly under the title/rename row,
        # in both modes -- it describes the *parameter*, not either value, so
        # it never moves depending on whether a reference is docked. Not a
        # boxed text widget, which read as another input
        # and claimed a fixed slab of height whatever its one sentence
        # needed. Selectable so it can still be copied.
        if parameter.description:
            desc = QLabel(parameter.description)
            desc.setObjectName("CardDescription")
            desc.setWordWrap(True)
            desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
            header_box.addWidget(desc)
        layout.addWidget(header_frame)

        body, self._body_layout = page_content()
        layout.addWidget(body)

        # "Main" role label: built lazily alongside the reference block
        # below, only while a reference is docked. It joins the editor's own
        # row (aligned-rows layout) so the editor and the reference value
        # share one label column and their values start at the same x.
        self._main_file_heading: QLabel | None = None

        self._editor = create_card(parameter, meta)
        self._editor.draft_changed.connect(self.draft_changed)
        self._editor.draft_reset.connect(self.draft_reset)
        self._editor.commit_requested.connect(self.commit_requested)
        self._editor.bulk_commit_requested.connect(self.bulk_commit_requested)
        self._value_row = QHBoxLayout()
        # Same spacing as the ledger rows' cluster/value gap -- with the
        # shared fixed label width this is what aligns the two value columns.
        self._value_row.setSpacing(style.ROLE_ROW_SPACING)
        self._value_row.addWidget(self._editor, 1)
        # Stretch 1: inert while the card sits at its natural height (the
        # Inspector top-aligns it), but this is what carries the pane's
        # leftover height down to a grid big enough to want it -- the
        # reference section below never absorbs it (see ``growable_grid``).
        self._body_layout.addLayout(self._value_row, 1)

        # Reference section: the "Main" role label plus the ledger, built
        # lazily, only once ``set_reference_groups`` is first called with
        # real content -- with no reference pinned this never runs, so the
        # card stays exactly today's, no extra widget instantiated at all.
        self._reference_ledger: ReferenceLedger | None = None
        #: Whether the reference section is currently meant to be showing.
        self._reference_active = False

    def set_reference_groups(
        self, groups: tuple[ValueGroup, ...], pins: list[ReferencePin]
    ) -> None:
        """Show/refresh/hide the reference ledger (design rule 3).

        *groups* is this parameter's per-value grouping over every pinned
        reference (``core.compare.group_reference_values``); empty when
        there is nothing to show (no reference pinned, or no pinned
        reference has this key) -- the "Main" label and ledger hide in
        every such case, returning the editor to the full row width.
        Populate-only: this never touches ``self._editor``'s draft/commit
        signals (known Qt pitfall), so calling it can never trip
        ``_touched``, whatever order it is called relative to construction
        -- it does, however, always tell the editor whether to overlay a
        table reference on its own live preview
        (:meth:`~.base.EditorCard.set_reference_table`), a no-op for any
        editor that is not table-shaped.
        """
        self._reference_active = bool(groups)
        if not self._reference_active:
            if self._main_file_heading is not None:
                self._main_file_heading.hide()
            if self._reference_ledger is not None:
                self._reference_ledger.hide()
            self._editor.set_reference_table(None)
            return
        if self._reference_ledger is None:
            self._main_file_heading = QLabel("Main")
            self._main_file_heading.setObjectName("MainFileHeading")
            # Into the editor's own row, not above it: the fixed label width
            # (matched by the ledger's badge-cluster column) is what aligns
            # the editor with the reference values below.
            self._main_file_heading.setFixedWidth(style.ROLE_LABEL_WIDTH)
            self._value_row.insertWidget(0, self._main_file_heading, 0, Qt.AlignTop)
            self._reference_ledger = ReferenceLedger()
            self._reference_ledger.pull_requested.connect(self.pull_requested)
            self._body_layout.addWidget(self._reference_ledger)
        specs = [self._row_spec(group, pins) for group in groups]
        self._reference_ledger.set_rows(specs)
        # The editor's own chart overlay stays single-series until Phase 2's
        # per-pin overlay lands: it shows the first differing table group.
        overlay = next(
            (spec.table[0] for spec in specs if spec.table is not None), None
        )
        self._editor.set_reference_table(overlay)
        self._main_file_heading.show()
        self._reference_ledger.show()

    def _row_spec(self, group: ValueGroup, pins: list[ReferencePin]) -> LedgerRowSpec:
        """One group's ledger-row content, classified the same way the
        single-reference block classified its value."""
        kind = classify(group.value, self._meta)
        table: tuple[list[list[object]], list[bool]] | None = None
        text, monospace, unit, width = "", False, "", None
        # A differing, table-representable value gets the richer treatment
        # (grid + chart overlay); an EQUAL table keeps the compact
        # one-liner, same as every other equal value.
        if not group.equals_main and table_is_representable(group.value):
            ref_rows = table_rows(group.value)
            main_rows = table_rows(self.parameter.value)
            if main_rows:
                matches = matching_table_rows(main_rows, ref_rows)
            else:
                # A non-table main (e.g. a function expression) cannot diff
                # row-by-row -- marking every row purple would read as pure
                # noise, so the whole grid stays quiet instead.
                matches = [True] * len(ref_rows)
            table = (ref_rows, matches)
        elif isinstance(group.value, str):
            # The full expression, not value_preview's truncated first
            # line -- that one-line form still serves the parameter
            # list row it was built for.
            text, monospace = group.value, True
            width = self._editor.reference_value_width()
        else:
            text = value_preview(group.value, kind)[0]
            unit = self.parameter.unit if kind in _UNIT_LABEL_KINDS else ""
            width = self._editor.reference_value_width()
        return LedgerRowSpec(
            pins=tuple(pins[index] for index in group.indices),
            text=text,
            monospace=monospace,
            same=group.equals_main,
            unit=unit,
            width=width,
            table=table,
            group=group,
        )

    def growable_grid(self):
        """The inner editor's grid, if it has one -- see
        ``EditorCard.growable_grid``."""
        return self._editor.growable_grid()

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

    def commit_open_subeditor(self) -> None:
        """Delegate to the inner editor -- see
        ``EditorCard.commit_open_subeditor``."""
        self._editor.commit_open_subeditor()

    def set_cell_issues(self, issues) -> None:
        """Pass the validator's per-cell diagnostics to the inner editor."""
        self._editor.set_cell_issues(issues)

    def set_validity(self, text: str, colour: str) -> None:
        """Drive the header's validity dot and text; validity decisions stay
        in the Inspector."""
        self._dot.setText(html_img(DOT, color=colour))
        self._badge.setText(text)

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
    # Inline rename row -- only built when ``self._renamable``
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
