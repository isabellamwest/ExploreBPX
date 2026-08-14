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
  (:func:`core.bpx_gateway.expected_fields`) that aren't already present, with
  container-link fields (which identify a child *section*, never an addable
  parameter) filtered out. These are highlighted in accent blue so the
  section's own standard fields stand out. A ``Particle``/``Validation``
  *collection itself* (as opposed to one of its named instances -- a
  material, a run -- which do resolve) still has no single schema definition
  to resolve at all, and simply has no suggested group -- not a dead end.
* **Other parameters** -- every remaining alias in the full BPX standard
  (:func:`core.bpx_gateway.searchable_parameters`) that this section doesn't
  expect and doesn't already have, in plain text.

A two-segment "Standard" | "Custom" tab strip (:class:`~ui_qt.cards.modal.
ModeStrip`, already used elsewhere for a Chart/Table toggle -- so it already
carries a tab role, not just a value-type picker) sits above everything else;
the popup always opens on **Standard**.

**Standard** is the list described above: typing filters both groups by
substring, and the "Create custom parameter" fallback is a **pinned footer
action**, not a scrolling row -- it stays put beneath the list (separated by
a divider), reachable by keyboard as the last navigable entry. Activating it
(click or Enter) switches to **Custom**, pre-filling Name with whatever text
was typed.

**Custom** is a plain form, shown directly rather than expanded in place: a
Name field, an optional Unit field, and a Scalar/Text/Boolean/Table/Series
type picker (Scalar checked by default). "Add" composes the key (``name``
plus `` [unit]`` when a unit is given) and seeds the value for the chosen
type -- ``0.0``/``""``/``False``/an empty table/an empty list -- so the new
parameter lands straight on its matching card (:mod:`ui_qt.cards`) instead of
the metadata-less raw fallback. If the composed key already names a
parameter in this section, "Add" refuses (a plain inline message explains
why) rather than silently overwriting it -- ``core.editing.add_parameter``
writes unconditionally, so this is the only guard against it. Cancel clears
the form and switches back to Standard.

A suggestion row (either group) skips the form entirely: it emits its known
alias with an honest empty value (``None``), letting
``core.commands.AddParameter``/the validator judge legality, not this widget;
a suggested alias always resolves its proper :class:`~core.bpx_gateway.FieldMeta`
on rebuild (it is, by definition, expected by the target section's own
schema). An "other" alias resolves its meaning the same schema-honest way BPX
itself does -- keyed by *(section, alias)*, not alias alone -- so it opens its
proper editor only if the target section's schema actually defines that
alias; otherwise it falls back to the metadata-less raw editor rather than
borrowing an unrelated section's meaning for the same alias.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from explore_bpx.core.bpx_gateway import ExpectedField, FieldMeta, expected_fields, searchable_parameters
from explore_bpx.core.parameter_types import extract_unit
from explore_bpx.ui_qt import parameter_row, style, typography
from explore_bpx.ui_qt.cards.modal import ModeStrip
from explore_bpx.ui_qt.dismissal import OutsideDismissFilter
from explore_bpx.ui_qt.floating_card import SHADOW_MARGIN as _SHADOW_MARGIN
from explore_bpx.ui_qt.floating_card import floating_card
from explore_bpx.ui_qt.parameter_row import ParameterRowDelegate

#: The Custom tab's type picker, in the order the row shows them, mapped to
#: the seed value each type commits when "Add" is pressed.
#: Chosen so ``core.parameter_types.classify`` (no schema metadata exists for
#: a custom alias) lands the new parameter on the matching kind -- SCALAR/
#: TEXT/BOOLEAN/TABLE/SERIES -- with an honest "nothing set yet" value for
#: that kind, never guessed data. ``classify`` itself is not touched: these
#: seeds are simply values it already routes correctly.
_CUSTOM_TYPE_SEEDS: dict[str, object] = {
    "Scalar": 0.0,
    "Text": "",
    "Boolean": False,
    "Table": {"x": [], "y": []},
    "Series": [],
}
_CUSTOM_TYPE_LABELS = tuple(_CUSTOM_TYPE_SEEDS)

#: Shown only while Scalar is the selected type -- a plain, honest warning
#: that the new parameter starts at a placeholder, not a real measurement.
_SCALAR_SEED_WARNING = "Scalar starts at 0.0 - set the real value on the card."

#: Shown when Name/Unit compose a key that already exists in this section --
#: refusing the add rather than letting ``core.editing.add_parameter``'s
#: unconditional ``parent[key] = value`` silently overwrite the existing
#: parameter's value.
_COLLISION_MESSAGE = "A parameter with this name already exists here."

#: Visible-row cap before the list scrolls; keeps the popup within screen
#: bounds however long the full standard gets. Counts every row (headers
#: included); the pinned "create" footer sits outside this budget.
_MAX_VISIBLE_ROWS = 10

#: Fixed width of the card's visible content.
_CARD_WIDTH = 380

_SUGGESTED_HEADER = "Suggested for this section"
_OTHER_HEADER = "Other parameters"

#: The popup's two tabs, in strip order. "Standard" is the grouped
#: BPX-alias list; "Custom" is the hand-typed parameter form. The popup
#: always opens on "Standard".
_TAB_LABELS = ("Standard", "Custom")


def _kind_label(meta) -> str | None:
    """A short, honest kind indication drawn from :class:`FieldMeta` flags, or
    ``None`` when nothing about the field's shape is actually known.

    Every label is verbatim BPX/JSON-schema vocabulary (``FloatFunctionTable``,
    ``dict[str, FloatInt]``, ...) rather than an invented paraphrase -- a
    standing project rule, since modellers read this against the schema they
    already know.

    An alias whose meaning differs across BPX sections (e.g.
    ``"Conductivity [S.m-1]"``, a plain scalar for an electrode but a
    function-capable field for the electrolyte) collapses in
    :func:`core.bpx_gateway.searchable_parameters` to an alias-only
    :class:`FieldMeta` with no description, no examples, and every type flag
    ``False`` -- the same shape a field with no meaningful flags would carry.
    Defaulting to "FloatInt" there would assert a kind that may well be
    wrong, so that shape omits the hint rather than guessing.
    """
    if meta.is_enum:
        return "enum"
    if meta.is_integer:
        return "int"
    if meta.is_text:
        return "str"
    if meta.is_series:
        return "list[FloatInt]"
    if meta.allows_map:
        return "FloatInt | dict[str, FloatInt]"
    if meta.allows_function:
        return "FloatFunctionTable"
    if not meta.description and not meta.examples:
        return None
    return "FloatInt"


def suggestion_row_text(alias: str, meta, required: bool = False) -> str:
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


def suggestion_row_html(alias: str, meta, tier: str, required: bool) -> str:
    """This row's rich-text fragment: the bare alias (its trailing unit
    bracket split off) bolded and coloured by *tier*, followed by the same
    kind/unit/"Required" hints ``suggestion_row_text`` renders as plain text --
    muted, except the "Required" tag itself.

    Shared with :mod:`ui_qt.parameter_list`'s "fields to add" group so the
    two "here is a field you could add" surfaces speak one visual
    language, not two independently-drifting ones.

    Requiredness colours **only that tag**, never the name: a required field
    is a suggested one, and recolouring its name would split the suggested
    group into two visual tiers when it is one."""
    name, unit = parameter_row.split_name_and_unit(alias)
    name_color = style.ACCENT if tier == "suggested" else style.DEFAULT_TEXT
    hints: list[tuple[str, str]] = []
    kind = _kind_label(meta)
    if kind:
        hints.append((kind, style.MUTED))
    if unit:
        hints.append((unit, style.MUTED))
    if required:
        hints.append(("Required", style.REQUIRED))
    return parameter_row.compose_row_html(name, hints, name_color=name_color)


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


class _SuggestionDelegate(ParameterRowDelegate):
    """Paints a faint divider above group headers that follow another group,
    so the "Other parameters" section reads as its own block, on top of
    :class:`ParameterRowDelegate`'s shared rich-text row rendering."""

    _GAP = 9  # extra top space carrying the divider, above a following header

    @staticmethod
    def _has_divider(index) -> bool:
        return bool(index.data(AddParameterPopup._TIER_TOP_ROLE))  # noqa: SLF001 - same-file delegate reads the popup's role

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
        painter.setPen(QPen(QColor(style.BORDER_FAINT)))
        line_y = rect.top() + self._GAP // 2
        painter.drawLine(rect.left() + 6, line_y, rect.right() - 6, line_y)
        painter.restore()
        shifted = QStyleOptionViewItem(option)
        shifted.rect = QRect(rect.left(), rect.top() + self._GAP, rect.width(), rect.height() - self._GAP)
        super().paint(painter, shifted, index)


class AddParameterPopup(QWidget):
    """Frameless popup with a "Standard" | "Custom" tab strip: Standard lists
    the whole BPX standard for a section (suggested fields highlighted) with
    a pinned custom-add footer; Custom is a plain hand-typed parameter form."""

    #: (key, seed) -- a suggestion row (either group) always carries seed
    #: ``None`` (the honest empty value); the Custom tab's form's "Add"
    #: carries whichever seed its selected type maps to
    #: (``_CUSTOM_TYPE_SEEDS``).
    custom_parameter_requested = Signal(str, object)

    _ALIAS_ROLE = Qt.UserRole
    #: Which tier a row belongs to -- "suggested", "other" or "header". Drives
    #: the highlight/plain distinction and lets tests assert tier membership
    #: without depending on rendered colour.
    _TIER_ROLE = Qt.UserRole + 1
    #: Marks a header that should carry a divider line above it (i.e. a group
    #: that follows another group).
    _TIER_TOP_ROLE = Qt.UserRole + 2
    #: Whether the section's schema requires this alias -- only ever true for
    #: a "suggested" row ("other" rows aren't scoped to this section's own
    #: required list). Drives the required colour/tag; kept as structured
    #: data so tests can assert it without depending on rendered colour.
    _REQUIRED_ROLE = Qt.UserRole + 3

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
        #: Which tab is on screen -- one of ``_TAB_LABELS``. The popup always
        #: opens on "Standard" (see ``open_for_section``).
        self._active_tab: str = _TAB_LABELS[0]

        self._tab_strip = ModeStrip(_TAB_LABELS, self._on_tab_clicked)
        self._tab_strip.select(0)

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
        # Long aliases wrap onto a second line rather than eliding or
        # scrolling sideways -- the whole hint must stay readable; a stray
        # horizontal scrollbar would otherwise steal height and trigger a
        # spurious vertical one under the content-hugging height.
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setWordWrap(True)
        self._list.setTextElideMode(Qt.ElideNone)
        # The search popup's own row metrics -- the two palettes are one
        # family, so their rows share one height.
        self._list.setItemDelegate(_SuggestionDelegate(self._list, h_pad=8, v_pad=6))
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
        self._create_button.clicked.connect(self._activate_footer)
        self._create_button.hide()

        self._form = self._build_custom_form()
        self._form.hide()

        card, card_layout = floating_card(self, "AddParameterCard", width=_CARD_WIDTH)
        self._card = card
        card_layout.addWidget(self._tab_strip)
        card_layout.addWidget(self._input)
        card_layout.addWidget(self._list)
        card_layout.addWidget(self._divider)
        card_layout.addWidget(self._create_button)
        card_layout.addWidget(self._form)

    # -- opening -----------------------------------------------------
    def open_for_section(
        self,
        anchor: QWidget,
        section_label: str,
        existing_aliases,
        section_path: tuple[str, ...] = (),
        model: str | None = None,
        section_value: object = None,
    ) -> None:
        """Show the popup under *anchor*, scoped to *section_label*.

        *existing_aliases* is the set of parameter labels already present in
        the target section, so nothing ever offers to silently overwrite one.
        *section_path*/*model*/*section_value* are used to look up the
        section's schema-expected aliases via
        :func:`core.bpx_gateway.expected_fields` (*section_value* is the
        section's live content, needed to discriminate the electrode
        single/blended union); sections the schema still cannot resolve
        (a ``Particle``/``Validation`` *collection itself*, as opposed to one
        of its named instances -- a material, a run -- which do resolve)
        raise :class:`ValueError`, which simply leaves the *suggested* group
        empty. The full BPX standard (the "other" group) is sourced from the
        schema index independently, so every section -- resolvable or not --
        still lists all its addable parameters.

        ``expected_fields`` returns *every* schema property of the resolved
        definition, including container-link fields that merely name a child
        *section* (e.g. a blended electrode's ``"Particle"``,
        ``Parameterisation``'s ``"Cell"``) -- its own docstring says callers
        must filter those out. This popup only ever offers *parameters*, so
        fields with ``meta.is_container`` are dropped here before they ever
        reach a row: offering ``"Particle"`` as an addable parameter would
        route through :func:`core.commands.AddParameter` ->
        :func:`core.editing.add_parameter`, an unconditional
        ``parent[key] = value`` that would silently replace the whole child
        section (every material, every parameter under it) with ``None``.
        """
        self._existing_aliases = frozenset(existing_aliases)
        try:
            fields = expected_fields(tuple(section_path), model, section_value)
        except ValueError:
            self._expected_fields = ()
            self._expected_aliases = frozenset()
        else:
            fields = tuple(field for field in fields if not field.meta.is_container)
            self._expected_aliases = frozenset(field.alias for field in fields)
            self._expected_fields = tuple(field for field in fields if field.alias not in self._existing_aliases)
        self._input.setPlaceholderText(f"Add parameter to {section_label}…")
        self._input.clear()
        self._refresh_rows("")
        self._reset_custom_form()
        self._set_active_tab(_TAB_LABELS[0])  # always reopen on Standard
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
                self._list.addItem(self._make_row(field.alias, field.meta, "suggested", required=field.required))
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
        item = QListWidgetItem(suggestion_row_text(alias, meta, required))
        item.setData(self._ALIAS_ROLE, alias)
        item.setData(self._TIER_ROLE, tier)
        item.setData(self._REQUIRED_ROLE, required)
        if tier == "suggested":
            item.setForeground(QColor(style.ACCENT))
            font = typography.semibold(self._list.font())
            item.setFont(font)
        item.setData(parameter_row.HTML_ROLE, suggestion_row_html(alias, meta, tier, required))
        return item

    def _make_header(self, text: str, divider: bool) -> QListWidgetItem:
        """A small, uppercase, non-selectable group label."""
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)  # visible, but never selected/activated
        item.setData(self._TIER_ROLE, "header")
        item.setForeground(QColor(style.MUTED))
        font = typography.semibold(typography.sized(self._list.font(), typography.META))
        font.setCapitalization(QFont.AllUppercase)
        typography.apply_caps_spacing(font)
        item.setFont(font)
        if divider:
            item.setData(self._TIER_TOP_ROLE, True)
        return item

    def _set_footer(self, show: bool) -> None:
        """Show/hide the pinned custom-add footer (and its divider) and keep
        its label in step with the typed text. Actual visibility also
        depends on the active tab -- see ``_update_footer_visibility``."""
        self._footer_shown = show
        if show:
            label = f"  Create custom parameter “{self._typed}”"
            # Elided into the fixed-width card (56: card margins + button
            # padding + icon) -- a native button clips a long typed name
            # with no ellipsis. The tooltip carries the whole sentence, the
            # app's usual elision contract (and the test seam: offscreen
            # fallback fonts make the elide point itself unpredictable).
            self._create_button.setToolTip(label.strip())
            self._create_button.setText(
                self._create_button.fontMetrics().elidedText(label, Qt.ElideRight, _CARD_WIDTH - 56)
            )
        self._update_footer_visibility()

    # -- tabs ----------------------------------------------------------
    def _on_tab_clicked(self, index: int) -> None:
        self._set_active_tab(_TAB_LABELS[index])

    def _set_active_tab(self, tab: str) -> None:
        """Show *tab*'s widgets, hide the other's, and keep the tab strip
        itself in step -- the single place every tab switch (open, a tab
        click, the footer, Cancel) goes through."""
        self._active_tab = tab
        standard = tab == _TAB_LABELS[0]
        self._tab_strip.select(0 if standard else 1)
        self._input.setVisible(standard)
        self._list.setVisible(standard)
        self._update_footer_visibility()
        self._form.setVisible(not standard)
        self._refit()
        if standard:
            self._input.setFocus()
        else:
            self._form_name.setFocus()
            self._form_name.selectAll()

    def _update_footer_visibility(self) -> None:
        """The pinned footer (and its divider) only ever shows on the
        Standard tab, and only while ``_footer_shown``."""
        visible = self._footer_shown and self._active_tab == _TAB_LABELS[0]
        self._divider.setVisible(visible)
        self._create_button.setVisible(visible)

    # -- custom-parameter form ------------------------------------------
    def _build_custom_form(self) -> QWidget:
        """Build (but do not show) the Custom tab's form: Name, an optional
        Unit, a Scalar/Text/Boolean/Table/Series type picker (plain text, no
        icons -- a standing project rule), the Scalar-only seed warning, a
        same-styled collision message, and Add/Cancel."""
        self._form_name = QLineEdit()
        self._form_name.setObjectName("AddParameterInput")  # same look as the search field
        self._form_name.setPlaceholderText("Name")

        self._form_unit = QLineEdit()
        self._form_unit.setObjectName("AddParameterInput")
        self._form_unit.setPlaceholderText("optional, e.g. V")

        self._form_type_strip = ModeStrip(_CUSTOM_TYPE_LABELS, self._on_form_type_changed)
        self._form_type_strip.select(0)  # Scalar, the default

        self._form_warning = QLabel(_SCALAR_SEED_WARNING)
        self._form_warning.setObjectName("Hint")
        self._form_warning.setWordWrap(True)

        #: Shown instead of submitting when the composed key already exists
        #: in this section (see ``_submit_custom_form``); same plain-label
        #: convention as ``_form_warning``, above it so it sits right next to
        #: the fields that caused it.
        self._form_message = QLabel(_COLLISION_MESSAGE)
        self._form_message.setObjectName("Hint")
        self._form_message.setWordWrap(True)
        self._form_message.hide()

        self._form_add = QPushButton("Add")
        self._form_add.setEnabled(False)

        self._form_cancel = QPushButton("Cancel")

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self._form_add)
        buttons.addWidget(self._form_cancel)
        buttons.addStretch(1)

        form = QWidget()
        form.setObjectName("CustomParameterForm")
        layout = QVBoxLayout(form)
        layout.setContentsMargins(10, 4, 10, 8)
        layout.setSpacing(6)
        layout.addWidget(self._form_name)
        layout.addWidget(self._form_unit)
        layout.addWidget(self._form_type_strip)
        layout.addWidget(self._form_warning)
        layout.addWidget(self._form_message)
        layout.addLayout(buttons)

        self._form_name.textChanged.connect(self._update_form_add_enabled)
        self._form_name.textChanged.connect(self._clear_collision_message)
        self._form_unit.textChanged.connect(self._clear_collision_message)
        self._form_add.clicked.connect(self._submit_custom_form)
        self._form_cancel.clicked.connect(self._cancel_custom_form)
        return form

    def _activate_footer(self, *_args) -> None:
        """The pinned footer's click handler: same switch-to-Custom route as
        Enter on the keyboard-selected footer (``_activate``)."""
        self._switch_to_custom_tab(self._typed)

    def _switch_to_custom_tab(self, prefill: str) -> None:
        """Switch to the Custom tab, pre-filling Name with *prefill* -- the
        search text the footer was offering to create -- and resetting
        Unit/type/messages to their defaults."""
        self._form_name.setText(prefill)
        self._form_unit.clear()
        self._form_type_strip.select(0)
        self._form_warning.setVisible(True)
        self._form_message.hide()
        self._update_form_add_enabled()
        self._set_active_tab(_TAB_LABELS[1])

    def _cancel_custom_form(self, *_args) -> None:
        """Cancel: clear the form's fields and switch back to Standard."""
        self._reset_custom_form()
        self._set_active_tab(_TAB_LABELS[0])

    def _reset_custom_form(self) -> None:
        """Clear the custom form back to its defaults -- shared by Cancel and
        by ``open_for_section``, so a freshly (re)opened popup never carries
        a previous section's stale Name/Unit/type/collision state."""
        self._form_name.clear()
        self._form_unit.clear()
        self._form_type_strip.select(0)
        self._form_warning.setVisible(True)
        self._form_message.hide()

    def _update_form_add_enabled(self, *_args) -> None:
        """Add stays disabled while Name is empty/whitespace -- there is
        nothing yet to key the new parameter with."""
        self._form_add.setEnabled(bool(self._form_name.text().strip()))

    def _on_form_type_changed(self, index: int) -> None:
        """The scalar-seed warning is only honest while Scalar is selected;
        the type never affects the composed key, but a stale collision
        message is cleared too, matching Name/Unit."""
        self._form_warning.setVisible(_CUSTOM_TYPE_LABELS[index] == "Scalar")
        self._clear_collision_message()

    def _clear_collision_message(self, *_args) -> None:
        self._form_message.hide()

    def _submit_custom_form(self, *_args) -> None:
        """Compose the key from Name/Unit and emit it with the seed the
        selected type maps to, then close the popup -- the same
        close-and-emit shape every other route through this popup uses.

        Refuses (and surfaces ``_form_message`` instead) when the composed
        key already names a parameter in this section: ``core.editing.
        add_parameter`` writes ``parent[key] = value`` unconditionally, so
        without this check a name/unit combination that happens to collide
        with an existing alias -- typed across the two separate fields,
        never matching anything the popup's own list/footer already guards
        against -- would silently overwrite that parameter's value.
        """
        name = self._form_name.text().strip()
        if not name:
            return
        unit = self._form_unit.text().strip()
        key = f"{name} [{unit}]" if unit else name
        if key in self._existing_aliases:
            self._form_message.show()
            self._refit()
            return
        label = _CUSTOM_TYPE_LABELS[self._form_type_strip.current_index()]
        self.hide()
        self.custom_parameter_requested.emit(key, _CUSTOM_TYPE_SEEDS[label])

    def _resize_list(self) -> None:
        """Size the list to hug its content -- no dead space, no premature
        scrollbar -- but cap it at ``_MAX_VISIBLE_ROWS`` so it scrolls natively
        instead of growing the popup off-screen."""
        count = self._list.count()
        if count == 0:
            self._list.setFixedHeight(0)
        else:
            frame = 2 * self._list.frameWidth()
            heights = [self._list.sizeHintForRow(i) for i in range(count)]
            if count > _MAX_VISIBLE_ROWS:
                self._list.setFixedHeight(sum(heights[:_MAX_VISIBLE_ROWS]) + frame)
            else:
                self._list.setFixedHeight(sum(heights) + frame)
        self._refit()

    def _refit(self) -> None:
        """Shrink the popup back to fit whatever it is currently showing --
        the list (after ``_resize_list``) or the Custom tab's form -- or dead
        space would linger from a taller prior state/tab. Two Qt details make
        this more than a bare ``adjustSize``: a top-level's layout sets the
        window's *minimum* size and only ever raises it (so a prior taller
        minimum would pin the height), and ``adjustSize`` reads a cached
        hint, so the layout must be re-activated first.
        """
        if not self.isVisible():
            return
        self.setMinimumHeight(0)
        self._list.updateGeometry()
        # The card's own layout holds the list/form, so it is the one whose
        # cached hint is stale; activating only the outer layout would resize
        # the window against the pre-change height.
        self._card.layout().invalidate()
        self._card.layout().activate()
        self.layout().activate()
        self.adjustSize()

    # -- selection / activation --------------------------------------
    def _selectable_rows(self) -> list[int]:
        """Row indices the keyboard/mouse may land on -- i.e. real parameter
        rows, skipping the non-selectable group headers."""
        return [i for i in range(self._list.count()) if self._list.item(i).flags() & Qt.ItemIsSelectable]

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
            if self._active_tab != _TAB_LABELS[1]:  # already there: don't re-seed it
                self._switch_to_custom_tab(self._typed)
            return
        item = self._list.currentItem()
        if item is None:
            return
        alias = item.data(self._ALIAS_ROLE)
        if not alias:
            return
        self.hide()
        self.custom_parameter_requested.emit(alias, None)

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
