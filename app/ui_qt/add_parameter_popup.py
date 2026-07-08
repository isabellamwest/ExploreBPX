"""Add-parameter popup: the custom-add surface for the parameter-list header.

Anchored under the Parameter-list pane's "+ Add parameter" button, following
the frameless ``Qt.FramelessWindowHint | Qt.Tool`` pattern established by
:class:`~ui_qt.search.SearchPopup` and
:class:`~ui_qt.parameter_info_popover.ParameterInfoPopover`. This is a new,
self-contained widget -- it owns both its text input and its single
actionable row, takes keyboard focus itself (Down/Up to move, Enter to
activate, staged Escape to close) and dismisses on focus-out. It does not
subclass or reuse :class:`~ui_qt.search.SearchBar`, which owns navigation and
must not gain an authoring role.

The popup is a unified surface. With empty input it lists every BPX alias the
schema expects for the target section that isn't already present. As the user
types, that list narrows and is joined by a second, visually de-emphasised
tier of every *other* BPX alias (from the full schema index) matching the
typed text -- surfacing the whole standard, not just what this section
expects -- alongside an always-available "Create custom parameter" fallback
row. All routes end the same way -- creating a parameter with an honest empty
value (``None``) and letting ``core.commands.AddParameter``/the validator
judge legality, not this widget; a known alias (expected or not) still
resolves its proper :class:`~core.bpx_gateway.FieldMeta` on rebuild because
metadata resolves by leaf alias regardless of section. For sections the
schema cannot resolve without content (the electrode union), the *expected*
tier degrades gracefully to none while the "other BPX alias" tier and the
custom row stay fully functional.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.bpx_gateway import ExpectedField, FieldMeta, expected_fields, metadata_index
from core.parameter_types import extract_unit
from ui_qt import style

_NO_SUGGESTIONS_TEXT = "Suggestions aren't available for this section yet."

#: Visible-row cap before the suggestion list scrolls; keeps the popup well
#: within screen bounds regardless of how long the expected/other-alias
#: tiers get.
_MAX_VISIBLE_ROWS = 10


def _kind_label(meta) -> str:
    """A short, honest kind indication drawn from :class:`FieldMeta` flags."""
    if meta.is_enum:
        return "Enum"
    if meta.is_integer:
        return "Integer"
    if meta.is_text:
        return "Text"
    if meta.allows_function:
        return "Number or Function"
    return "Number"


def _suggestion_text(alias: str, meta, required: bool = False) -> str:
    hints = [_kind_label(meta)]
    unit = extract_unit(alias)
    if unit:
        hints.append(unit)
    if required:
        hints.append("Required")
    return f"{alias}  ({' · '.join(hints)})"


class _PopupInput(QLineEdit):
    """The popup's own line edit; keeps key/focus handling local to the
    popup instead of reusing ``SearchBar``."""

    move_requested = Signal(int)
    activate_requested = Signal()
    escape_requested = Signal()
    focus_lost = Signal()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Down, Qt.Key_Up):
            self.move_requested.emit(1 if key == Qt.Key_Down else -1)
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.activate_requested.emit()
            return
        if key == Qt.Key_Escape:
            self.escape_requested.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        self.focus_lost.emit()
        super().focusOutEvent(event)


class AddParameterPopup(QWidget):
    """Frameless popup offering BPX-alias suggestions plus a custom-add
    fallback for a section."""

    custom_parameter_requested = Signal(str)  # the chosen alias (suggested or typed)

    _ALIAS_ROLE = Qt.UserRole
    #: Which tier a row belongs to -- "expected", "other" or "custom". Drives
    #: the grey/highlighted visual distinction and lets tests assert tier
    #: membership without depending on rendered colour.
    _TIER_ROLE = Qt.UserRole + 1

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AddParameterPopup")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedWidth(320)

        self._existing_aliases: frozenset[str] = frozenset()
        self._expected_fields: tuple[ExpectedField, ...] = ()
        #: The section's full expected-alias set (schema order, *not*
        #: filtered for presence) -- excluded from the "other BPX alias" tier
        #: so an expected field never appears twice under a different tier.
        self._expected_aliases: frozenset[str] = frozenset()

        self._input = _PopupInput()
        self._input.textChanged.connect(self._refresh_rows)
        self._input.move_requested.connect(self._move_selection)
        self._input.activate_requested.connect(self._activate)
        self._input.escape_requested.connect(self._on_escape)
        self._input.focus_lost.connect(self.hide)

        self._hint_label = QLabel()
        self._hint_label.setObjectName("AddParameterPopupHint")
        self._hint_label.setWordWrap(True)
        self._hint_label.hide()

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.itemClicked.connect(self._activate)

        layout = QVBoxLayout(self)
        layout.addWidget(self._input)
        layout.addWidget(self._hint_label)
        layout.addWidget(self._list)

    # -- opening -----------------------------------------------------
    def open_for_section(
        self,
        anchor: QWidget,
        section_label: str,
        existing_aliases,
        section_path: tuple[str, ...] = (),
        model: str | None = None,
    ) -> None:
        """Show the popup under *anchor*, scoped to *section_label*.

        *existing_aliases* is the set of parameter labels already present in
        the target section, so neither a suggestion nor the custom-add row
        ever offers to silently overwrite one. *section_path*/*model* are
        used to look up the section's schema-expected aliases via
        :func:`core.bpx_gateway.expected_fields`; sections the schema cannot
        resolve without content (e.g. the electrode single/blended union)
        raise :class:`ValueError`, which degrades the *expected* tier to none.
        That's caught tightly around the expected-set lookup only: the
        "other BPX alias" tier is sourced from the full schema index
        independently of section resolution, so it (and the custom-add row)
        stay fully functional even for an unresolvable section.
        """
        self._existing_aliases = frozenset(existing_aliases)
        try:
            fields = expected_fields(tuple(section_path), model)
        except ValueError:
            self._expected_fields = ()
            self._expected_aliases = frozenset()
            self._hint_label.setText(_NO_SUGGESTIONS_TEXT)
            self._hint_label.show()
        else:
            self._expected_aliases = frozenset(field.alias for field in fields)
            self._expected_fields = tuple(
                field for field in fields if field.alias not in self._existing_aliases
            )
            self._hint_label.hide()
        self._input.setPlaceholderText(f"Add parameter to {section_label}…")
        self._input.clear()
        self._refresh_rows("")
        bottom_left = anchor.mapToGlobal(anchor.rect().bottomLeft())
        self.move(bottom_left)
        self.show()
        self._input.setFocus(Qt.PopupFocusReason)

    # -- rows --------------------------------------------------------
    def _refresh_rows(self, text: str) -> None:
        """Rebuild the suggestion list for *text*.

        Empty input lists every expected-but-absent alias (the substring
        needle is empty, so it matches everything). Non-empty input narrows
        that expected tier and adds a second, de-emphasised tier of matching
        BPX aliases the section doesn't expect, before the custom-add
        fallback row (typed text only, per the existing coexistence rule).
        """
        self._list.clear()
        typed = text.strip()
        needle = typed.lower()
        shown_aliases: set[str] = set()

        for candidate in self._expected_fields:
            if needle in candidate.alias.lower():
                self._list.addItem(
                    self._make_row(
                        candidate.alias, candidate.meta, "expected", required=candidate.required
                    )
                )
                shown_aliases.add(candidate.alias)

        if typed:
            for alias, meta in self._other_matches(needle):
                self._list.addItem(self._make_row(alias, meta, "other"))
                shown_aliases.add(alias)

        if typed and typed not in self._existing_aliases and typed not in shown_aliases:
            item = QListWidgetItem(f"Create custom parameter: '{typed}'")
            item.setData(self._ALIAS_ROLE, typed)
            item.setData(self._TIER_ROLE, "custom")
            self._list.addItem(item)

        if self._list.count():
            self._list.setCurrentRow(0)
        self._resize_list()

    def _other_matches(self, needle: str) -> list[tuple[str, FieldMeta]]:
        """BPX aliases from the full schema index that match *needle* but
        aren't expected for this section and aren't already present, in a
        stable alphabetical order."""
        exclude = self._expected_aliases | self._existing_aliases
        matches = [
            (alias, meta)
            for alias, meta in metadata_index().items()
            if alias not in exclude and needle in alias.lower()
        ]
        matches.sort(key=lambda pair: pair[0].lower())
        return matches

    def _make_row(self, alias: str, meta, tier: str, required: bool = False) -> QListWidgetItem:
        item = QListWidgetItem(_suggestion_text(alias, meta, required))
        item.setData(self._ALIAS_ROLE, alias)
        item.setData(self._TIER_ROLE, tier)
        if tier == "other":
            item.setForeground(QColor(style.MUTED))
        return item

    def _resize_list(self) -> None:
        """Cap the list's visible height so it scrolls natively instead of
        growing the popup past a sensible size (or off-screen)."""
        count = self._list.count()
        if count == 0:
            self._list.setMaximumHeight(0)
            return
        row_height = self._list.sizeHintForRow(0)
        rows = min(count, _MAX_VISIBLE_ROWS)
        self._list.setMaximumHeight(row_height * rows + 2 * self._list.frameWidth())

    def _activate(self, *_args) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        alias = item.data(self._ALIAS_ROLE)
        if not alias:
            return
        self.hide()
        self.custom_parameter_requested.emit(alias)

    # -- keyboard ------------------------------------------------------
    def _move_selection(self, delta: int) -> None:
        count = self._list.count()
        if not count:
            return
        row = (self._list.currentRow() + delta) % count
        self._list.setCurrentRow(row)

    def _on_escape(self) -> None:
        """Staged Escape: clear typed text first, then close the popup."""
        if self._input.text():
            self._input.clear()
        else:
            self.hide()
