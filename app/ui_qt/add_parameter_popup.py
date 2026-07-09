"""Add-parameter popup: the custom-add surface for the parameter-list header.

Anchored under the Parameter-list pane's "+ Add parameter" button, following
the frameless ``Qt.FramelessWindowHint | Qt.Tool`` pattern established by
:class:`~ui_qt.search.SearchPopup` and
:class:`~ui_qt.parameter_info_popover.ParameterInfoPopover`. This is a new,
self-contained widget -- it owns both its text input and its actionable rows,
takes keyboard focus itself (Down/Up to move, Enter to activate, staged Escape
to close) and dismisses on an outside click via the shared
:class:`~ui_qt.dismissal.OutsideDismissFilter`. It does not subclass or reuse
:class:`~ui_qt.search.SearchBar`, which owns navigation and must not gain an
authoring role.

The popup is a floating command palette (a rounded, shadowed card over a
translucent top-level, à la Raycast / Linear / VS Code Quick Open). It lists
the *whole* BPX standard for the target section up front -- no typing required
-- under at most two headed groups:

* **Suggested** -- the aliases the BPX schema expects for *this* section
  (:func:`core.bpx_gateway.expected_fields`) that aren't already present. These
  are highlighted in accent blue so the section's own standard fields stand
  out. Sections whose schema is an unresolvable union (the electrode
  single/blended case) simply have no suggested group -- not a dead end.
* **Other parameters** -- every remaining alias in the full BPX standard
  (:func:`core.bpx_gateway.searchable_parameters`) that this section doesn't
  expect and doesn't already have, in plain text.

Typing filters both groups by substring. The "Create custom parameter"
fallback is a **pinned footer action**, not a scrolling row: it stays put
beneath the list (separated by a divider), reachable by keyboard as the last
navigable entry. All routes end the same way -- creating a parameter with an
honest empty value (``None``) and letting ``core.commands.AddParameter``/the
validator judge legality, not this widget; a suggested alias always resolves
its proper :class:`~core.bpx_gateway.FieldMeta` on rebuild (it is, by
definition, expected by the target section's own schema). An "other" alias
resolves its meaning the same schema-honest way BPX itself does -- keyed by
*(section, alias)*, not alias alone -- so it opens its proper editor only if
the target section's schema actually defines that alias; otherwise it falls
back to the metadata-less raw editor rather than borrowing an unrelated
section's meaning for the same alias.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from core.bpx_gateway import ExpectedField, FieldMeta, expected_fields, searchable_parameters
from core.parameter_types import extract_unit
from ui_qt import style
from ui_qt.dismissal import OutsideDismissFilter

#: Visible-row cap before the list scrolls; keeps the popup within screen
#: bounds however long the full standard gets. Counts every row (headers
#: included); the pinned "create" footer sits outside this budget.
_MAX_VISIBLE_ROWS = 10

#: Fixed width of the card's visible content.
_CARD_WIDTH = 380
#: Transparent margin around the card, giving the drop shadow room to render
#: without being clipped by the top-level's bounds.
_SHADOW_MARGIN = 16

_SUGGESTED_HEADER = "Suggested for this section"
_OTHER_HEADER = "Other parameters"


def _kind_label(meta) -> str | None:
    """A short, honest kind indication drawn from :class:`FieldMeta` flags, or
    ``None`` when nothing about the field's shape is actually known.

    An alias whose meaning differs across BPX sections (e.g.
    ``"Conductivity [S.m-1]"``, a plain scalar for an electrode but a
    function-capable field for the electrolyte) collapses in
    :func:`core.bpx_gateway.searchable_parameters` to an alias-only
    :class:`FieldMeta` with no description, no examples, and every type flag
    ``False`` -- the same shape a field with no meaningful flags would carry.
    Defaulting to "Number" there would assert a kind that may well be wrong,
    so that shape omits the hint rather than guessing.
    """
    if meta.is_enum:
        return "Enum"
    if meta.is_integer:
        return "Integer"
    if meta.is_text:
        return "Text"
    if meta.allows_function:
        return "Number or Function"
    if not meta.description and not meta.examples:
        return None
    return "Number"


def _suggestion_text(alias: str, meta, required: bool = False) -> str:
    hints = []
    kind = _kind_label(meta)
    if kind:
        hints.append(kind)
    unit = extract_unit(alias)
    if unit:
        hints.append(unit)
    if required:
        hints.append("Required")
    if not hints:
        return alias
    return f"{alias}  ({' · '.join(hints)})"


def _render_icon(size: int, paint) -> QIcon:
    """Draw a crisp (2x-supersampled) monochrome glyph via *paint(painter, px)*."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    paint(painter, size * scale)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


def _search_icon() -> QIcon:
    def paint(p: QPainter, px: float) -> None:
        pen = QPen(QColor(style.MUTED))
        pen.setWidthF(px * 0.09)
        p.setPen(pen)
        radius = px * 0.26
        cx, cy = px * 0.40, px * 0.40
        p.drawEllipse(QPointF(cx, cy), radius, radius)
        p.drawLine(QPointF(cx + radius * 0.72, cy + radius * 0.72), QPointF(px * 0.86, px * 0.86))

    return _render_icon(14, paint)


def _plus_icon() -> QIcon:
    def paint(p: QPainter, px: float) -> None:
        pen = QPen(QColor(style.ACCENT))
        pen.setWidthF(px * 0.11)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        mid, arm = px * 0.5, px * 0.28
        p.drawLine(QPointF(mid, mid - arm), QPointF(mid, mid + arm))
        p.drawLine(QPointF(mid - arm, mid), QPointF(mid + arm, mid))

    return _render_icon(14, paint)


class _PopupInput(QLineEdit):
    """The popup's own line edit; keeps key/focus handling local to the
    popup instead of reusing ``SearchBar``."""

    move_requested = Signal(int)
    activate_requested = Signal()
    escape_requested = Signal()

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


class _SuggestionDelegate(QStyledItemDelegate):
    """Paints a faint divider above group headers that follow another group,
    so the "Other parameters" section reads as its own block."""

    _GAP = 9  # extra top space carrying the divider, above a following header

    @staticmethod
    def _has_divider(index) -> bool:
        return bool(index.data(AddParameterPopup._TIER_TOP_ROLE))

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if self._has_divider(index):
            size.setHeight(size.height() + self._GAP)
        return size

    def paint(self, painter, option, index) -> None:
        if not self._has_divider(index):
            super().paint(painter, option, index)
            return
        rect = option.rect
        painter.save()
        painter.setPen(QPen(QColor("#eaecef")))
        line_y = rect.top() + self._GAP // 2
        painter.drawLine(rect.left() + 6, line_y, rect.right() - 6, line_y)
        painter.restore()
        shifted = QStyleOptionViewItem(option)
        shifted.rect = QRect(
            rect.left(), rect.top() + self._GAP, rect.width(), rect.height() - self._GAP
        )
        super().paint(painter, shifted, index)


class AddParameterPopup(QWidget):
    """Frameless popup listing the whole BPX standard for a section (suggested
    fields highlighted) plus a pinned custom-add footer."""

    custom_parameter_requested = Signal(str)  # the chosen alias (suggested or typed)

    _ALIAS_ROLE = Qt.UserRole
    #: Which tier a row belongs to -- "suggested", "other" or "header". Drives
    #: the highlight/plain distinction and lets tests assert tier membership
    #: without depending on rendered colour.
    _TIER_ROLE = Qt.UserRole + 1
    #: Marks a header that should carry a divider line above it (i.e. a group
    #: that follows another group).
    _TIER_TOP_ROLE = Qt.UserRole + 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AddParameterPopup")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedWidth(_CARD_WIDTH + 2 * _SHADOW_MARGIN)
        #: The "+ Add parameter" trigger button is deliberately not registered
        #: as "inside" -- clicking it while the popup is open must
        #: close-and-swallow (reading as a toggle) rather than reopen.
        self._dismiss_filter = OutsideDismissFilter(self)

        self._existing_aliases: frozenset[str] = frozenset()
        self._expected_fields: tuple[ExpectedField, ...] = ()
        #: The section's full expected-alias set (schema order, *not* filtered
        #: for presence) -- excluded from the "other" tier so a suggested field
        #: never appears twice under a different group.
        self._expected_aliases: frozenset[str] = frozenset()
        #: The currently typed text the footer would create, and whether that
        #: footer is shown / keyboard-selected.
        self._typed: str = ""
        self._footer_shown: bool = False
        self._footer_selected: bool = False

        self._input = _PopupInput()
        self._input.setObjectName("AddParameterInput")
        self._input.addAction(_search_icon(), QLineEdit.LeadingPosition)
        self._input.textChanged.connect(self._refresh_rows)
        self._input.move_requested.connect(self._move_selection)
        self._input.activate_requested.connect(self._activate)
        self._input.escape_requested.connect(self._on_escape)

        self._list = QListWidget()
        self._list.setObjectName("AddParameterList")
        self._list.setFocusPolicy(Qt.NoFocus)
        # Long aliases elide with "…" rather than scrolling sideways -- a stray
        # horizontal scrollbar would otherwise steal height and trigger a
        # spurious vertical one under the content-hugging height.
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setTextElideMode(Qt.ElideRight)
        self._list.setItemDelegate(_SuggestionDelegate(self._list))
        self._list.itemClicked.connect(self._on_row_clicked)

        #: Thin rule separating the scrolling list from the pinned footer;
        #: shown only alongside the footer.
        self._divider = QFrame()
        self._divider.setObjectName("AddParameterDivider")
        self._divider.setFixedHeight(1)
        self._divider.hide()

        self._create_button = QPushButton()
        self._create_button.setObjectName("AddParameterCreate")
        self._create_button.setIcon(_plus_icon())
        self._create_button.setFocusPolicy(Qt.NoFocus)
        self._create_button.setCursor(Qt.PointingHandCursor)
        self._create_button.clicked.connect(self._emit_custom)
        self._create_button.hide()

        card = QFrame()
        card.setObjectName("AddParameterCard")
        card.setFixedWidth(_CARD_WIDTH)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(6)
        card_layout.addWidget(self._input)
        card_layout.addWidget(self._list)
        card_layout.addWidget(self._divider)
        card_layout.addWidget(self._create_button)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(15, 23, 42, 60))
        shadow.setOffset(0, 5)
        card.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            _SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN
        )
        outer.addWidget(card)

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
        the target section, so nothing ever offers to silently overwrite one.
        *section_path*/*model* are used to look up the section's schema-expected
        aliases via :func:`core.bpx_gateway.expected_fields`; sections the
        schema cannot resolve without content (e.g. the electrode
        single/blended union) raise :class:`ValueError`, which simply leaves
        the *suggested* group empty. The full BPX standard (the "other" group)
        is sourced from the schema index independently, so every section --
        resolvable or not -- still lists all its addable parameters.
        """
        self._existing_aliases = frozenset(existing_aliases)
        try:
            fields = expected_fields(tuple(section_path), model)
        except ValueError:
            self._expected_fields = ()
            self._expected_aliases = frozenset()
        else:
            self._expected_aliases = frozenset(field.alias for field in fields)
            self._expected_fields = tuple(
                field for field in fields if field.alias not in self._existing_aliases
            )
        self._input.setPlaceholderText(f"Add parameter to {section_label}…")
        self._input.clear()
        self._refresh_rows("")
        bottom_left = anchor.mapToGlobal(anchor.rect().bottomLeft())
        # Offset by the shadow margin so the visible card -- not the transparent
        # padding -- aligns with the anchor's left edge, leaving a small gap.
        self.move(bottom_left - QPoint(_SHADOW_MARGIN, 0))
        self.show()
        self._dismiss_filter.install()
        # Row-height metrics are only reliable once shown/polished, so re-fit
        # the list now that the first (empty-input) build is on screen.
        self._resize_list()
        self._input.setFocus(Qt.PopupFocusReason)

    # -- rows --------------------------------------------------------
    def _refresh_rows(self, text: str) -> None:
        """Rebuild the grouped list (and the footer) for *text*.

        Empty input lists the whole standard (the needle matches everything);
        typing filters both groups by substring. The "Suggested" group is
        omitted entirely when the section has no resolvable expected fields, so
        such sections just show the full "other" list with no header.
        """
        self._list.clear()
        typed = text.strip()
        needle = typed.lower()
        shown_aliases: set[str] = set()

        suggested = [f for f in self._expected_fields if needle in f.alias.lower()]
        others = self._other_matches(needle)

        if suggested:
            self._list.addItem(self._make_header(_SUGGESTED_HEADER, divider=False))
            for field in suggested:
                self._list.addItem(
                    self._make_row(field.alias, field.meta, "suggested", required=field.required)
                )
                shown_aliases.add(field.alias)

        if others:
            # Only head (and divide) the "other" group when a suggested group
            # precedes it; on its own it needs no label.
            if suggested:
                self._list.addItem(self._make_header(_OTHER_HEADER, divider=True))
            for alias, meta in others:
                self._list.addItem(self._make_row(alias, meta, "other"))
                shown_aliases.add(alias)

        self._typed = typed
        show_footer = bool(typed) and typed not in self._existing_aliases and typed not in shown_aliases
        self._set_footer(show_footer)

        self._reset_selection()
        self._resize_list()

    def _other_matches(self, needle: str) -> list[tuple[str, FieldMeta]]:
        """Every BPX alias from the full schema index that matches *needle* but
        isn't expected for this section and isn't already present, in a stable
        alphabetical order. With an empty needle this is the whole standard."""
        exclude = self._expected_aliases | self._existing_aliases
        matches = [
            (alias, meta)
            for alias, meta in searchable_parameters().items()
            if alias not in exclude and needle in alias.lower()
        ]
        matches.sort(key=lambda pair: pair[0].lower())
        return matches

    def _make_row(self, alias: str, meta, tier: str, required: bool = False) -> QListWidgetItem:
        item = QListWidgetItem(_suggestion_text(alias, meta, required))
        item.setData(self._ALIAS_ROLE, alias)
        item.setData(self._TIER_ROLE, tier)
        if tier == "suggested":
            item.setForeground(QColor(style.ACCENT))
            font = QFont(self._list.font())
            font.setBold(True)
            item.setFont(font)
        return item

    def _make_header(self, text: str, divider: bool) -> QListWidgetItem:
        """A small, uppercase, non-selectable group label."""
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)  # visible, but never selected/activated
        item.setData(self._TIER_ROLE, "header")
        item.setForeground(QColor(style.MUTED))
        font = QFont(self._list.font())
        size = font.pointSizeF()
        if size > 0:
            font.setPointSizeF(size * 0.82)
        font.setBold(True)
        font.setCapitalization(QFont.AllUppercase)
        font.setLetterSpacing(QFont.PercentageSpacing, 106)
        item.setFont(font)
        if divider:
            item.setData(self._TIER_TOP_ROLE, True)
        return item

    def _set_footer(self, show: bool) -> None:
        """Show/hide the pinned custom-add footer (and its divider) and keep
        its label in step with the typed text."""
        self._footer_shown = show
        self._divider.setVisible(show)
        self._create_button.setVisible(show)
        if show:
            self._create_button.setText(f"  Create custom parameter “{self._typed}”")

    def _resize_list(self) -> None:
        """Size the list to hug its content -- no dead space, no premature
        scrollbar -- but cap it at ``_MAX_VISIBLE_ROWS`` so it scrolls natively
        instead of growing the popup off-screen."""
        count = self._list.count()
        if count == 0:
            self._list.setFixedHeight(0)
            return
        frame = 2 * self._list.frameWidth()
        heights = [self._list.sizeHintForRow(i) for i in range(count)]
        if count > _MAX_VISIBLE_ROWS:
            self._list.setFixedHeight(sum(heights[:_MAX_VISIBLE_ROWS]) + frame)
        else:
            self._list.setFixedHeight(sum(heights) + frame)

    # -- selection / activation --------------------------------------
    def _selectable_rows(self) -> list[int]:
        """Row indices the keyboard/mouse may land on -- i.e. real parameter
        rows, skipping the non-selectable group headers."""
        return [
            i
            for i in range(self._list.count())
            if self._list.item(i).flags() & Qt.ItemIsSelectable
        ]

    def _reset_selection(self) -> None:
        """Pick the default highlight after a rebuild: the first real row if
        any, else the footer, so Enter always has an obvious target."""
        rows = self._selectable_rows()
        if rows:
            self._select_footer(False)
            self._list.setCurrentRow(rows[0])
        elif self._footer_shown:
            self._select_footer(True)
        else:
            self._select_footer(False)
            self._list.setCurrentRow(-1)

    def _select_footer(self, on: bool) -> None:
        """Move the keyboard highlight onto (or off) the pinned footer,
        restyling it and clearing the list's own selection so only one row
        ever looks active."""
        self._footer_selected = on and self._footer_shown
        self._create_button.setProperty("selected", self._footer_selected)
        self._create_button.style().unpolish(self._create_button)
        self._create_button.style().polish(self._create_button)
        if self._footer_selected:
            self._list.setCurrentRow(-1)

    def _on_row_clicked(self, item: QListWidgetItem) -> None:
        if not (item.flags() & Qt.ItemIsSelectable):
            return  # a group header -- not actionable
        self._list.setCurrentItem(item)
        self._activate()

    def _activate(self, *_args) -> None:
        if self._footer_selected and self._footer_shown:
            self._emit_custom()
            return
        item = self._list.currentItem()
        if item is None:
            return
        alias = item.data(self._ALIAS_ROLE)
        if not alias:
            return
        self.hide()
        self.custom_parameter_requested.emit(alias)

    def _emit_custom(self, *_args) -> None:
        if not self._typed:
            return
        self.hide()
        self.custom_parameter_requested.emit(self._typed)

    # -- keyboard ------------------------------------------------------
    def _move_selection(self, delta: int) -> None:
        """Cycle the highlight through the real rows (skipping headers) and, as
        the final entry, the pinned footer -- so the whole surface is
        keyboard-reachable even though headers and the footer aren't rows."""
        rows = self._selectable_rows()
        total = len(rows) + (1 if self._footer_shown else 0)
        if not total:
            return
        if self._footer_selected:
            current = len(rows)
        else:
            cur_row = self._list.currentRow()
            current = rows.index(cur_row) if cur_row in rows else 0
        new = (current + delta) % total
        if self._footer_shown and new == len(rows):
            self._select_footer(True)
        else:
            self._select_footer(False)
            self._list.setCurrentRow(rows[new])

    def _on_escape(self) -> None:
        """Staged Escape: clear typed text first, then close the popup."""
        if self._input.text():
            self._input.clear()
        else:
            self.hide()
