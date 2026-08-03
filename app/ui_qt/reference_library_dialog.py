"""``ReferenceLibraryDialog``: browse the bundled PyBaMM reference sets and
choose one to dock as the workspace Reference.

A pure chooser: it holds no app state and never docks anything itself --
accepting simply reports :meth:`selected_set_id` and the caller routes it through
``AppState.open_reference_set``. The sets carry no ``Validation`` runs
(PyBaMM parameter sets hold no cycling data), which is why this exists
apart from the run-comparison ``DatabaseExamplesDialog``; see the
"Bundled PyBaMM parameter sets" entry in ``docs/future.md``.

**Layout.** Picker rows on the left (curated order, short title + muted
model; selection is a purple border plus a small plain tick -- the standing
rule: never circled tick/cross badges anywhere in the app), beside a detail
card reusing the reference group-box chrome. The detail shows the chosen
file's own Header fields verbatim -- Title, Model, References, Description
(each set's conversion caveats live in its Description, and they must be
readable *before* docking) -- plus section/parameter counts derived through
:class:`core.document.BPXDocument`, the same derivation the docked tile
itself uses, and ``core.reference_library.PROVENANCE`` in the footer: these
are derived artifacts under someone else's licence, so origin and citation
belong on screen rather than in a ``NOTICE.md`` no packaged user can open.
Chen2020 (the curated flagship, always first) is pre-selected
so the detail pane is never empty and the dock button never needs a
disabled placeholder state. A future second source (LiionDB, ...) becomes
another picker group in this same dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.document import BPXDocument
from core.reference_library import (
    PROVENANCE,
    ReferenceSet,
    list_reference_sets,
    load_reference_raw,
)

from .style import BORDER, MUTED, REFERENCE
from .titles import panel_title

#: The picker column's fixed width -- the run-comparison dialog's rail width.
_PICKER_WIDTH = 250


class _SetRow(QFrame):
    """One selectable reference set: short title beside its muted model.

    Selection is a purple (``style.REFERENCE``) border plus a small plain
    tick, the exact ``_PickerRow`` treatment from the run-comparison dialog
    -- single-select here, so clicking a row selects it (never toggles it
    off; there is always exactly one chosen set)."""

    clicked = Signal()

    def __init__(self, ref_set: ReferenceSet, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ReferenceLibraryRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        name = QLabel(ref_set.short_title)
        name.setWordWrap(True)
        layout.addWidget(name, 1)

        model = QLabel(ref_set.model)
        model.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        layout.addWidget(model)

        self._tick = QLabel("✓")
        self._tick.setStyleSheet(f"color: {REFERENCE}; font-weight: 600;")
        self._tick.hide()
        layout.addWidget(self._tick)

        self.set_selected(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self._tick.setVisible(selected)
        border = f"2px solid {REFERENCE}" if selected else f"1px solid {BORDER}"
        self.setStyleSheet(
            f"QFrame#ReferenceLibraryRow {{ border: {border}; border-radius: 4px; }}"
        )


class ReferenceLibraryDialog(QDialog):
    """Choose one bundled reference set -- see the module docstring."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reference library")
        self.resize(720, 430)

        self._sets = list_reference_sets()
        self._rows: dict[str, _SetRow] = {}
        self._selected_id = ""
        #: ``set_id -> (section_count, parameter_count)``: the counts need a
        #: full ``BPXDocument`` build, so each set pays for it once.
        self._counts: dict[str, tuple[int, int]] = {}

        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_picker())
        body.addWidget(self._build_detail(), 1)
        layout.addLayout(body, 1)
        layout.addLayout(self._build_footer())

        if self._sets:
            self._select(self._sets[0].id)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_picker(self) -> QWidget:
        container = QWidget()
        container.setFixedWidth(_PICKER_WIDTH)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        heading = panel_title("Bundled PyBaMM sets")
        layout.addWidget(heading)

        for ref_set in self._sets:
            row = _SetRow(ref_set)
            row.clicked.connect(lambda set_id=ref_set.id: self._select(set_id))
            self._rows[ref_set.id] = row
            layout.addWidget(row)

        layout.addStretch(1)
        return container

    def _build_detail(self) -> QWidget:
        """The detail card: the reference group-box chrome (purple band,
        light "Read-only" tag), filled from the chosen set in
        :meth:`_select`."""
        card = QFrame()
        card.setObjectName("ReferenceGroupBox")
        box = QVBoxLayout(card)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        header = QWidget()
        header.setObjectName("ReferenceGroupBoxHeader")
        header.setAttribute(Qt.WA_StyledBackground, True)
        band = QHBoxLayout(header)
        band.setContentsMargins(12, 5, 12, 5)
        band.setSpacing(8)
        self._detail_heading = QLabel()
        self._detail_heading.setObjectName("ReferenceHeading")
        band.addWidget(self._detail_heading)
        band.addStretch(1)
        tag = QLabel("Read-only")
        tag.setObjectName("ReferenceReadOnlyTag")
        band.addWidget(tag)
        box.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 10, 12, 12)
        body_layout.setSpacing(8)
        self._detail_title = QLabel()
        self._detail_title.setObjectName("WorkspaceCardTitle")
        self._detail_title.setWordWrap(True)
        body_layout.addWidget(self._detail_title)
        self._detail_meta = QLabel()
        self._detail_meta.setObjectName("ReferenceLibraryMeta")
        self._detail_meta.setWordWrap(True)
        body_layout.addWidget(self._detail_meta)
        #: The citation, lifted out of the Description paragraph it is buried
        #: in -- attribution has to be scannable, not something a reader has
        #: to mine a thousand characters of conversion caveats to find.
        self._detail_citation = QLabel()
        self._detail_citation.setObjectName("ReferenceLibraryCitation")
        self._detail_citation.setWordWrap(True)
        self._detail_citation.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body_layout.addWidget(self._detail_citation)
        self._detail_description = QLabel()
        self._detail_description.setObjectName("ReferenceLibraryDescription")
        self._detail_description.setWordWrap(True)
        self._detail_description.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        body_layout.addWidget(self._detail_description)
        body_layout.addStretch(1)
        provenance = QLabel(PROVENANCE)
        provenance.setObjectName("ReferenceLibraryProvenance")
        provenance.setWordWrap(True)
        body_layout.addWidget(provenance)
        box.addWidget(body, 1)
        return card

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        hint = QLabel("Docks as the read-only Reference · replaces any docked reference")
        hint.setObjectName("Hint")
        footer.addWidget(hint)
        footer.addStretch(1)
        buttons = QDialogButtonBox()
        self._dock_button = buttons.addButton("Dock as reference", QDialogButtonBox.AcceptRole)
        self._dock_button.setObjectName("ReferenceLibraryDockButton")
        self._dock_button.setDefault(True)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        return footer

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def selected_set_id(self) -> str:
        """The chosen set's id ("pybamm/chen2020"); "" only if the bundled
        assets are missing entirely (the caller treats that as cancel)."""
        return self._selected_id

    def _select(self, set_id: str) -> None:
        self._selected_id = set_id
        for row_id, row in self._rows.items():
            row.set_selected(row_id == set_id)
        ref_set = next(s for s in self._sets if s.id == set_id)
        self._detail_heading.setText(ref_set.short_title)
        self._detail_title.setText(ref_set.title)
        sections, parameters = self._set_counts(set_id)
        self._detail_meta.setText(
            f"Model {ref_set.model or '-'} · {sections} sections · {parameters} parameters"
        )
        # An uncurated future file may carry no References at all; show
        # nothing rather than a bare "Source:".
        self._detail_citation.setText(f"Source: {ref_set.references}" if ref_set.references else "")
        self._detail_citation.setVisible(bool(ref_set.references))
        self._detail_description.setText(ref_set.description)

    def _set_counts(self, set_id: str) -> tuple[int, int]:
        if set_id not in self._counts:
            document = BPXDocument.from_raw(
                load_reference_raw(set_id), filename=set_id, fmt="json"
            )
            self._counts[set_id] = (document.section_count, document.parameter_count)
        return self._counts[set_id]
