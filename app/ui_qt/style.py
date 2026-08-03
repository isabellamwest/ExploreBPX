"""Calm, information-dense palette and stylesheet for the desktop frontend.

A single global stylesheet keeps the look consistent (an IDE/XMLSpy feel)
rather than scattering ad-hoc styling across widgets. Colours are muted; accent
use is reserved for validity status only.
"""

from __future__ import annotations

from core.completion import TaskKind
from core.validation import Severity

# ---------------------------------------------------------------------------
# Spacing/type scale: shared step values so new layout code picks a rung on
# the app's existing rhythm instead of inventing its own margin/font-size
# literal. Not a migration -- existing hardcoded numbers stay put until a
# later pass moves them onto these names; these constants only need to exist
# so new code has somewhere to reach for.
# ---------------------------------------------------------------------------
SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 12
SPACING_LG = 16

FONT_SIZE_SM = 11
FONT_SIZE_BASE = 12
FONT_SIZE_MD = 13
FONT_SIZE_LG = 15

#: A readable-measure cap for a content column inside an otherwise full-bleed
#: section (e.g. the Inspector's ``cards/page.py`` content body) -- long
#: lines of prose/labels stay legible instead of stretching edge-to-edge with
#: the pane.
CONTENT_MEASURE = 560

OK = "#2e7d32"
ERROR = "#c62828"
WARNING = "#ef6c00"
ACCENT = "#1f6feb"
#: Pale accent tint shared by every "selected row"/"hovered chip" wash that
#: isn't a severity or reference colour: list-selection backgrounds, the
#: Diagnostics rail's selected entry, and the add-parameter popup's pinned
#: Create action -- one blue instead of three near-identical ones (#ddeeff,
#: #e3edfd, #eaf2ff) that had drifted apart. ``RAIL_SELECTED_BG`` reads this
#: constant directly; the raw stylesheet below still spells the same hex
#: literal at each QSS selector (as every other named colour already does in
#: that string, e.g. ``BORDER_STRONG``/``HEADER_BAND_STRONG``) rather than
#: turning ``STYLESHEET`` into an f-string, which would need every literal
#: ``{``/``}`` in the QSS escaped.
ACCENT_TINT = "#ddeeff"
#: The reference-file feature's own accent: purple, by explicit user
#: decision -- everything reference-specific carries this one hue so it is
#: visually unmistakable, and it can never be confused with ``ACCENT`` (the
#: app's general blue) or any severity colour. Used by the Workspace
#: reference card's tag; ghost rows/sections are expected to reuse it.
REFERENCE = "#6f42c1"
#: A required-but-absent/required-parameter tint -- distinct from both
#: ``ERROR`` (invalid) and ``ACCENT`` (a merely-suggested field), so a
#: schema-required parameter reads as its own, readable, amber category in
#: the add-parameter popup and the parameter list.
REQUIRED = "#9a6700"
BORDER = "#d0d7de"
#: Wash behind a grid cell the validator blamed -- a background tint, so it
#: reads distinctly from ``ERROR``, which is used as text/badge colour.
ERROR_TINT = "#ffebe9"
#: Warning-badge background on the Diagnostics page rail -- the
#: ``WARNING`` counterpart to ``ERROR_TINT``.
WARNING_TINT = "#fff1e0"
#: Pale wash behind a REF_ONLY ghost row/the comparison strip -- the
#: ``REFERENCE`` counterpart to ``ERROR_TINT``/``WARNING_TINT``.
REFERENCE_TINT = "#f3ecfa"
#: The reference purple's pale border tone -- already used by the inspector
#: reference block's chrome in the stylesheet below (#d5cde6); named here so
#: the Source page's ← pull chip draws its outline from the same tint.
REFERENCE_BORDER = "#d5cde6"
#: Mid reference tone between ``REFERENCE`` and ``REFERENCE_BORDER``: the
#: outline of the hollow "reference only" gutter bar in the parameter list
#: (:data:`~ui_qt.parameter_row.REF_BAR_ROLE`) -- lighter than the solid
#: "differs" bar so a ghost row reads as an outline, not a fill, while
#: staying visibly purple at 3px.
REFERENCE_SOFT = "#a08cc4"
#: The Source page's value chip: the wash behind a value that differs
#: between the two panes. Warm but its own tint -- "differs" is
#: information, not a severity, so it is deliberately
#: darker than ``WARNING_TINT`` (it must read at value-chip size) while
#: staying out of the error/warning families.
DIFF_TINT = "#ffdfb8"
#: Neutral grey badge background: the "All sections" rail entry's total
#: badge and every "outstanding" count badge (rail/pane), which are never
#: red/amber -- "outstanding is not an error" kept visible in the colour
#: itself.
NEUTRAL_TINT = "#eef0f2"
#: Muted/de-emphasised text. Used for secondary labels (e.g. QLabel#Heading)
#: and reused as the foreground for the add-parameter popup's "other BPX
#: alias" suggestion tier (aliases the section doesn't expect), so grey rows
#: draw from the same palette rather than a one-off colour.
MUTED = "#57606a"
#: The app's default (untinted) text colour -- matches the base ``QWidget``
#: rule in the stylesheet below; named here so a "plain" row's name can be
#: coloured explicitly, the same as every other tier, rather than left to
#: whatever the delegate happens to inherit.
DEFAULT_TEXT = "#1f2328"
#: Ghosted value-preview text (matches the disabled-button foreground in
#: the stylesheet below): quieter than ``MUTED`` so a placeholder reads as
#: "nothing here", not as a value.
GHOST_TEXT = "#8c959f"
#: Diagnostics page rail: background distinct from the white detail
#: pane, and the selected entry's accent-tinted background/hover wash.
RAIL_BG = "#f3f4f6"
RAIL_SELECTED_BG = ACCENT_TINT
RAIL_HOVER_BG = "#e8eaed"
#: One step darker than the app's usual ``#d0d7de`` border tone, used only
#: on the Diagnostics page's own chrome (group-box border, rail's right
#: edge, strip's bottom edge, chip borders) so those regions read a touch
#: more defined without raising contrast anywhere else in the app.
#: Fills/palette are otherwise unchanged -- flat colour only, no shadows.
BORDER_STRONG = "#c4cdd5"
#: The faintest border tone: dividers and disabled-control outlines. One of
#: exactly three border greys, with ``BORDER`` and ``BORDER_STRONG``.
BORDER_FAINT = "#eaecef"
#: Slightly stronger shaded band for the Diagnostics group-box header row --
#: one step darker than the app's usual ``#f6f8fa`` banded-header tone.
HEADER_BAND_STRONG = "#eef1f4"
#: Chart grid lines (both QtCharts widgets: ``TablePreview`` and
#: ``MultiSeriesChart``). Lighter than ``BORDER`` so the grid recedes behind
#: the data; named here so the two charts draw from one source instead of
#: re-declaring it locally (they once drifted apart doing exactly that).
CHART_GRID = "#eaeef2"

# ---------------------------------------------------------------------------
# Tooltip vocabulary: the app's four completion/severity
# symbols (● red error, ● amber warning, ○ hollow missing, ◐ half added-no-
# value) each carry one fixed, generic tooltip sentence, chosen by the
# *enum* the layers already own -- never by a diagnostic's message text or
# ``error_type`` string, and never by a task's own alias/path text. This is
# deliberate and load-bearing (explicit user requirement): a future bpx
# wording change must never be able to make a tooltip lie, so every function
# below takes ONLY a ``core.validation.Severity`` or a
# ``core.completion.TaskKind`` -- there is no code path here that can even
# see a message string. One place for the whole vocabulary (this module),
# reused by the Diagnostics page (rail/strip/pane) and the Inspector's
# Issues tab so the two issue surfaces never drift.
# ---------------------------------------------------------------------------

_SEVERITY_TOOLTIPS: dict[Severity, str] = {
    Severity.ERROR: "Error - the BPX validator rejected this",
    Severity.WARNING: "Warning - flagged by the BPX validator",
}

_TASK_KIND_TOOLTIPS: dict[TaskKind, str] = {
    TaskKind.MISSING_FIELD: "Required field not yet added",
    TaskKind.MISSING_SECTION: "Required section not yet added",
    TaskKind.NULL_FIELD: "Added, but no value yet",
    TaskKind.DECLARE_MODEL: "Model not yet declared",
}


def severity_tooltip(severity: Severity) -> str:
    """The fixed, generic tooltip for a ●-severity row (an issue's dot, a
    strip chip, a rail badge). Takes only the ``Severity`` enum bpx's own
    diagnostic already carries -- never a message or ``error_type`` string."""
    return _SEVERITY_TOOLTIPS[severity]


def task_kind_tooltip(kind: TaskKind) -> str:
    """The fixed, generic tooltip for a ○/◐ task-glyph row. Takes only the
    app-owned ``TaskKind`` enum -- never a task's own alias/path text, which
    names the specific field/section, not the *kind* of work outstanding."""
    return _TASK_KIND_TOOLTIPS[kind]


def _count_phrase(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


def error_count_tooltip(count: int) -> str:
    return _count_phrase(count, "validator error")


def warning_count_tooltip(count: int) -> str:
    return _count_phrase(count, "validator warning")


def outstanding_count_tooltip(count: int) -> str:
    return _count_phrase(count, "outstanding item")


def counts_tooltip(error_count: int, warning_count: int, outstanding_count: int) -> str:
    """Compose a combined tooltip from whichever counts are nonzero (e.g. a
    rail entry showing both an error and an outstanding badge) -- "quiet"
    like the badges themselves: a zero count contributes no clause at all."""
    parts = []
    if error_count:
        parts.append(error_count_tooltip(error_count))
    if warning_count:
        parts.append(warning_count_tooltip(warning_count))
    if outstanding_count:
        parts.append(outstanding_count_tooltip(outstanding_count))
    return " · ".join(parts)


#: Shown on a value editor's unit label when the *parameter's own name* is a
#: fixed BPX schema property (``not core.structure.can_rename_parameter(path,
#: value)``) -- never on a user-owned or schema-undefined custom parameter's
#: unit, which the user typed themselves. Nothing louder than a tooltip: the
#: unit is still shown plainly, this only explains why it cannot be edited
#: here.
FIXED_UNIT_TOOLTIP = "Fixed by the BPX schema"

#: Widest a single-value input (scalar/enum/FloatInt line edit or combo) may
#: grow (structured-page layout): sized to the values it holds, not the pane,
#: so the unit label sits beside the value instead of at the pane's far edge.
#: Grids, tables and expressions still take the full width -- their content
#: genuinely uses it.
VALUE_INPUT_MAX_WIDTH = 280

#: Narrower cap for the integer stepper -- counts are short and the spin
#: buttons already widen it.
SPIN_INPUT_MAX_WIDTH = 160


def all_clear(text: str) -> str:
    """Prefix *text* with the app's one "all clear" glyph (a plain check),
    used by every "nothing outstanding" empty-row message (Diagnostics'
    Issues/Outstanding lists, the Inspector's Issues tab) so the three
    surfaces never drift onto their own check-mark spelling."""
    return "✓ " + text


def validity_pill_qss(background: str) -> str:
    """Inline stylesheet for a document-validity pill (white text on
    *background*) -- the parameter card's per-card badge. (The workspace
    panel used to share this; it has since replaced the pill with the
    dot-plus-plain-text language.)"""
    return f"color: white; background: {background}; padding: 2px 9px; border-radius: 4px;"


#: The toast pill's action link -- ``ACCENT`` is illegible on the pill's
#: dark ink ground, so the link carries the accent's light-on-dark tone
#: instead (QSS cannot reach into rich text; the toast inlines this).
TOAST_ACTION = "#79b8ff"


def toast_qss() -> str:
    """Inline stylesheet for the app's one toast pill (``ui_qt.toast.Toast``):
    a dark, ink-coloured pill with light text, matching the app's other
    floating surfaces (rounded corners) rather than a flat banner."""
    return (
        f"background: {DEFAULT_TEXT}; color: #ffffff; "
        "padding: 8px 18px; border-radius: 14px; font-size: 12px;"
    )


STYLESHEET = """
QWidget { font-size: 13px; color: #1f2328; }
QMainWindow, QWidget#Panel { background: #ffffff; }
QToolBar { background: #f6f8fa; border-bottom: 1px solid #d0d7de; padding: 4px; spacing: 8px; }
/* Toolbar buttons (Save/Export/Undo/Redo), styled as one family. The
   native Windows style hangs Export's menu-indicator caret below the text
   baseline, tight against the label, where it reads as a stray comma;
   fixing that needs padding on the button, which switches it to
   stylesheet rendering -- so all four buttons get the same flat treatment
   (the ActivityButton/SecondaryTab hover language) rather than leaving
   Export a one-off. Child selector on purpose: a descendant selector
   would also catch the search box's internal clear button. */
QToolBar > QToolButton { background: transparent; border: none; border-radius: 4px; padding: 3px 8px; }
QToolBar > QToolButton:hover:!disabled { background: #e8eaed; }
QToolBar > QToolButton:disabled { color: #8c959f; }
/* Menu-carrying buttons (Export, the material map's "Material"): reserve
   room on the right and centre the caret in it, clear of the label. The
   material button sits in a card's grid button row, not the toolbar, so the
   flat treatment its padding forfeits is restated for it here. */
QToolButton#ExportButton { padding-right: 22px; }
QToolButton#AddMaterialButton {
    background: transparent; border: none; border-radius: 4px;
    padding: 3px 8px; padding-right: 22px;
}
QToolButton#AddMaterialButton:hover { background: #e8eaed; }
QToolButton#ExportButton::menu-indicator,
QToolButton#AddMaterialButton::menu-indicator {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    right: 6px;
}
QTreeView, QListWidget { border: 1px solid #d0d7de; background: #ffffff; }
QTreeView::item, QListWidget::item { padding: 3px 4px; }
/* #ddeeff below is style.ACCENT_TINT, spelled as a literal (see the
   constant's comment for why) -- every list-selection/hover wash in this
   stylesheet reuses this same tint. */
QListWidget::item:selected, QTreeView::item:selected { background: #ddeeff; color: #1f2328; }
/* Editor page: the tree and parameter-list panes sit flush against the
   splitter's own 1px hairline (see QSplitter#EditorSplitter::handle below),
   so their own borders are stripped to avoid a doubled seam. Explicit ids
   only -- a descendant selector here would out-specify (and silently strip
   the border from) QListWidget#AddParameterList below. */
QTreeView#StructureTree, QListWidget#ParameterListView { border: none; outline: none; }
/* Wider than the generic 3px/4px item padding above -- a wrapped, two-line
   parameter row (name plus unit, or a validator marker) needs the extra
   breathing room the same way the add-parameter popup's rows do. */
QListWidget#ParameterListView::item { padding: 6px 8px; border-radius: 4px; }
/* The editor page's tree/params/inspector splitter: a single 1px hairline
   per seam. Scoped by objectName so it does not affect the Inspector's own
   internal (top/bottom) splitter, whose handle stays at its default width. */
QSplitter#EditorSplitter::handle { background: #d0d7de; }
QLabel#CardTitle { font-size: 15px; font-weight: 600; }
QLabel#CardSymbol { margin-left: 8px; }
/* Heading tiers. Fixed panel/section labels the app authors are one caps
   tier -- 11px MUTED
   caps, letter-spaced in code via titles.panel_title (QSS has no
   text-transform). Data-derived headings (document names, parse summaries)
   stay sentence-case ink as QLabel#Heading, the content tier. */
QLabel#PanelTitle { color: #57606a; font-weight: 600; font-size: 11px; }
QLabel#Heading { color: #1f2328; font-weight: 600; }
QLabel#CardDescription { color: #57606a; }
/* Structured-page inspector: the editing pane is a white page -- frameless
   scroll area, white content surface -- with each
   card's header block closed by a single full-bleed hairline. The gutter and
   rhythm live in cards/page.py; only the surfaces are painted here. */
QScrollArea#InspectorScroll { border: none; background: #ffffff; }
QWidget#InspectorContent { background: #ffffff; }
QFrame#CardPageHeader { border: none; border-bottom: 1px solid #d0d7de; }
QLabel#InspectorPlaceholder { color: #57606a; }
/* Unit labels sit directly beside their input (never at the pane edge) and
   stay quiet: they annotate the value, they are not part of it. */
QLabel#UnitLabel, QLabel#ReferenceUnitLabel { color: #57606a; }
QFrame#Card { border: 1px solid #d0d7de; border-radius: 6px; }
/* Workspace page: the Diagnostics page's own anatomy reused -- a shaded
   fixed-width actions rail beside a
   white pane holding the document and reference as banded-header group
   boxes. White ground; the earlier canvas tint, floating cards and solid
   validity pill are gone. Validity is the dot language (ui_qt.icons.DOT
   beside plain text), exactly as the Diagnostics strip chips draw it. The
   reference box carries the feature's purple (style.REFERENCE) on its
   header band, heading and Read-only tag only -- never louder than the
   document box. */
QWidget#WorkspacePage, QWidget#WorkspacePane { background: #ffffff; }
QWidget#WorkspaceRail { background: #f3f4f6; border-right: 1px solid #c4cdd5; }
QFrame#WorkspaceRailDivider { background: #d0d7de; border: none; }
/* Rail action buttons: white chips on the shaded rail, the Diagnostics
   strip-chip treatment (never native grey widgets). The old
   Open-as-reference chip moved onto the reference card and takes the
   tile-button treatment below. */
QPushButton#WorkspaceOpen {
    background: #ffffff; border: 1px solid #c4cdd5; border-radius: 6px;
    padding: 5px 10px; font-size: 12px; text-align: left;
}
QPushButton#WorkspaceOpen:hover { background: #eef1f4; }
/* One New-chooser model row: flat bold name button over a muted descriptor
   (list-row language). Property selector on purpose -- the buttons keep
   their per-model NewButton_{model} objectNames as the test/driver seam,
   which QSS cannot prefix-match. */
QPushButton[modelOption="true"] {
    background: transparent; border: none; border-radius: 4px;
    padding: 3px 6px; font-weight: 600; text-align: left;
}
QPushButton[modelOption="true"]:hover { background: #e8eaed; }
QLabel#NewChooserDescriptor { color: #57606a; font-size: 12px; padding: 0 6px 2px 6px; }
/* The two file group boxes: the Diagnostics group-box language (bordered
   rounded card, shaded banded header). The reference box swaps the band and
   border to the reference purple's own pale tints. */
QFrame#WorkspaceGroupBox { background: #ffffff; border: 1px solid #c4cdd5; border-radius: 6px; }
QWidget#WorkspaceGroupBoxHeader {
    background: #eef1f4; border-bottom: 1px solid #c4cdd5;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QFrame#ReferenceGroupBox { background: #ffffff; border: 1px solid #d5cde6; border-radius: 6px; }
QWidget#ReferenceGroupBoxHeader {
    background: #f6f2fb; border-bottom: 1px solid #d5cde6;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QLabel#WorkspaceCardTitle { font-size: 15px; font-weight: 600; }
QLabel#WorkspaceCardTitle:disabled { color: #8c959f; font-weight: 400; }
QLabel#WorkspaceCardKey { color: #57606a; }
/* The reference box's panel title keeps its purple identity while joining
   the caps tier -- colour is identity, caps is hierarchy. */
QLabel#ReferenceHeading { color: #6f42c1; font-weight: 600; font-size: 11px; }
/* Quieter than the heading beside it (explicit user call): a light, small
   annotation, not a badge. */
QLabel#ReferenceReadOnlyTag { color: #7a63ad; font-size: 10px; }
QPushButton#ReferenceTileMakeMain, QPushButton#ReferenceTileRemove,
QPushButton#ReferenceFromLibrary, QPushButton#WorkspaceOpenReference {
    background: #ffffff; border: 1px solid #d0d7de; border-radius: 4px;
    padding: 3px 10px; font-size: 12px;
}
QPushButton#ReferenceTileMakeMain:hover, QPushButton#ReferenceTileRemove:hover,
QPushButton#ReferenceFromLibrary:hover, QPushButton#WorkspaceOpenReference:hover { background: #f6f8fa; }
/* The reference card's empty state: the teaching line over the two dock
   buttons -- muted text, never a badge. */
QLabel#ReferenceEmptyStateText { color: #57606a; font-size: 12px; }
/* Reference library dialog: detail card reuses the ReferenceGroupBox
   chrome above; these are its own bits.
   The dock button is the dialog's one loud action -- the CopyUpButton's
   solid style.REFERENCE treatment. */
QLabel#ReferenceLibraryMeta { color: #57606a; font-size: 12px; }
QLabel#ReferenceLibraryCitation { color: #454c54; font-size: 12px; }
QLabel#ReferenceLibraryDescription {
    color: #454c54; font-size: 12px;
    border-left: 2px solid #d5cde6; padding-left: 8px;
}
QLabel#ReferenceLibraryProvenance { color: #8c959f; font-size: 11px; }
QPushButton#ReferenceLibraryDockButton {
    background: #6f42c1; color: #ffffff; font-weight: 600;
    border: none; border-radius: 4px; padding: 5px 14px;
}
QPushButton#ReferenceLibraryDockButton:hover { background: #5a3399; }
/* Comparison strip: the slim reference-aware band atop the parameter
   list. Purple identity (style.REFERENCE), muted counts. */
QWidget#ComparisonStrip { background: #f8f5fc; border-bottom: 1px solid #d0d7de; }
QLabel#ComparisonStripIdentity { color: #6f42c1; font-weight: 600; font-size: 12px; }
QLabel#ComparisonStripCounts { color: #57606a; font-size: 12px; }
/* Reference row: "Main file"/"Reference file" are plain bold micro-labels
   above their own value; the purple frame+tint
   marks only the read-only value box itself, not the whole row -- the unit
   label and "Copy up" button sit outside it, mirroring how the main
   editable row shows its own unit label outside the input. The "same as
   main" faint style reuses the app's muted-text tone via a dynamic
   property, the same pattern QLabel#DiagnosticsChip[chipOff="true"]
   already uses below. */
QLabel#MainFileHeading { color: #57606a; font-weight: 600; font-size: 11px; }
QLabel#ReferenceFileHeading { color: #6f42c1; font-weight: 600; font-size: 11px; }
QFrame#ReferenceValueBox { border: 1px solid #6f42c1; border-radius: 6px; background: #f8f5fc; }
QLabel#ReferenceBlockValue[same="true"] { color: #8c959f; }
/* "Copy up": the reference feature's first solid button -- solid
   style.REFERENCE fill, white text, so it reads as a deliberate, loud
   action beside the row's otherwise flat/bordered treatment. Disabled (an
   EQUAL row -- nothing to copy) fades to the same light-purple/muted-text
   pairing QPushButton#AddParameterButton:disabled already uses for "not
   available right now", not a full grey-out. */
QPushButton#CopyUpButton {
    background: #6f42c1; color: #ffffff; font-weight: 600;
    border: none; border-radius: 4px; padding: 4px 12px;
}
QPushButton#CopyUpButton:hover:!disabled { background: #5a3399; }
QPushButton#CopyUpButton:disabled { background: #d5cde6; color: #8c959f; font-weight: 400; }
QLabel#GhostCardHeading { color: #6f42c1; font-weight: 600; }
/* Source page toolbar: the fold-all toggle sits left in both modes;
   single-pane also shows the main file's identity + the purple docking
   hint. The bordered button reuses the reference tile's flat treatment. */
QLabel#SourceFileLabel { color: #57606a; font-size: 12px; }
QLabel#SourceHint { color: #6f42c1; font-size: 12px; }
QPushButton#SourceFoldButton {
    background: #ffffff; border: 1px solid #d0d7de; border-radius: 4px;
    padding: 2px 10px; font-size: 12px; color: #57606a;
}
QPushButton#SourceFoldButton:hover { background: #f6f8fa; }
/* Stale-reference band: slim, neutral, under the pane headers; the
   Reload link is the page's only blue. */
QWidget#SourceStaleBand { background: #eef0f2; }
QLabel#SourceStaleText { color: #57606a; font-size: 12px; }
QPushButton#SourceReloadLink {
    background: transparent; border: none; color: #1f6feb;
    font-size: 12px; padding: 0;
}
QPushButton#SourceReloadLink:hover { color: #1a5fd0; }
QStatusBar { background: #f6f8fa; border-top: 1px solid #d0d7de; font-size: 12px; color: #57606a; }
QWidget#ActivityBar { background: #f6f8fa; border-right: 1px solid #d0d7de; }
QToolButton#ActivityButton { background: transparent; border: none; border-left: 2px solid transparent; }
QToolButton#ActivityButton:hover:!checked { background: #e8eaed; }
QToolButton#ActivityButton:checked { border-left: 2px solid #1f2328; background: transparent; }
QWidget#PageHeader { background: #ffffff; border-bottom: 1px solid #d0d7de; }
QLabel#PageHeaderTitle { color: #57606a; font-size: 11px; font-weight: 600; }
QWidget#SecondaryTabStrip { background: #f6f8fa; }
QToolButton#SecondaryTab {
    background: transparent; border: none; border-top: 2px solid transparent;
    padding: 4px 12px; font-size: 12px; color: #57606a;
}
QToolButton#SecondaryTab:hover:!checked { background: #e8eaed; }
QToolButton#SecondaryTab:checked {
    color: #1f2328; font-weight: 600; border-top: 2px solid #1f6feb;
}
QListWidget#IssuesList { border: none; background: #ffffff; font-size: 12px; }
/* The toolbar search's floating results card: identical treatment to
   QFrame#AddParameterCard (translucent top-level, rounded shadowed card),
   so the app's two floating palettes read as one family. */
QFrame#SearchPopupCard {
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 10px;
}
QListWidget#SearchPopupList {
    border: none;
    background: transparent;
    outline: none;
}
QListWidget#SearchPopupList::item { padding: 6px 8px; border-radius: 4px; }
QListWidget#SearchPopupList::item:selected { background: #ddeeff; color: #1f2328; }
/* The Diagnostics page: a summary strip over a fixed-width rail beside a
   detail pane. The rail's own background is distinct from the white pane
   so the two read as separate surfaces, like the activity bar beside the
   editor. The strip/rail/group-box/chip border lines use BORDER_STRONG
   (#c4cdd5), one step darker than the app's usual #d0d7de, so this page's
   own regions read a touch more defined -- flat colour only, no shadows,
   and nothing outside this page's chrome changed. */
QWidget#DiagnosticsSummaryStrip { background: #f9fafb; border-bottom: 1px solid #c4cdd5; }
/* One strip chip: a small bordered, rounded card on the shaded strip
   band, distinct from the flat text it replaced. Each chip is a
   click-toggle filter; its "off" state is a dynamic QSS property
   (chipOff="true", set via setProperty + style().polish(), the same
   pattern QPushButton#AddParameterCreate's own "selected" property already
   uses below) -- a visibly muted/pressed-out card, never a hidden one
   (toggling never removes the chip itself, only what it filters). */
QLabel#DiagnosticsChip {
    background: #ffffff; border: 1px solid #c4cdd5; border-radius: 6px; padding: 4px 10px;
}
QLabel#DiagnosticsChip[chipOff="true"] { background: #eef0f2; border: 1px solid #d0d7de; }
QListWidget#DiagnosticsRail { background: #f3f4f6; border: none; border-right: 1px solid #c4cdd5; outline: none; }
QListWidget#DiagnosticsRail::item { padding: 0; border: none; }
QLabel#DiagnosticsPaneHeader { font-size: 14px; padding-bottom: 2px; }
/* The "N hidden by filters" line -- quiet, muted, never mistakable for a
   pinned empty-state (those use the shared muted-message row colour too,
   but this one only ever appears alongside real, still-counted rows). */
QLabel#DiagnosticsHiddenLine { color: #57606a; font-size: 12px; padding: 2px 2px; }
/* One group box: a bordered, rounded card with a shaded, banded header
   row -- the same "IDE panel" language as QFrame#Card elsewhere. The header
   band uses HEADER_BAND_STRONG (#eef1f4), one step darker than the app's
   usual #f6f8fa banded-header tone. */
QFrame#DiagnosticsGroupBox { background: #ffffff; border: 1px solid #c4cdd5; border-radius: 6px; }
QWidget#DiagnosticsGroupBoxHeader {
    background: #eef1f4; border-bottom: 1px solid #c4cdd5;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QLabel#DiagnosticsGroupBoxTitle { color: #57606a; font-weight: 600; font-size: 11px; }
/* The ratio/count tail ("· 3 of 6 added") stays sentence-case beside the
   caps title -- counts are information, not chrome. */
QLabel#DiagnosticsGroupBoxTitleSuffix { color: #57606a; font-size: 11px; }
QListWidget#DiagnosticsGroupBoxList { border: none; background: transparent; }
QListWidget#DiagnosticsGroupBoxList::item { padding: 6px 8px; border-radius: 4px; }
QListWidget#DiagnosticsGroupBoxList::item:hover { background: #f0f2f4; }
QListWidget#DiagnosticsGroupBoxList::item:selected { background: #ddeeff; color: #1f2328; }
/* "All sections", the backup view: one continuous list, same row rhythm
   as everywhere else in the app. */
QListWidget#DiagnosticsAllSectionsList { border: none; }
QListWidget#DiagnosticsAllSectionsList::item { padding: 6px 8px; border-radius: 4px; }
QListWidget#DiagnosticsAllSectionsList::item:hover { background: #f0f2f4; }
QListWidget#DiagnosticsAllSectionsList::item:selected { background: #ddeeff; color: #1f2328; }
QLabel#IssuesPlaceholder { color: #57606a; font-size: 12px; padding: 16px; }
QLabel#DocumentationPlaceholder { color: #57606a; font-size: 12px; padding: 16px; }
QLabel#Hint { color: #57606a; font-size: 11px; }

/* Mode strip: segmented buttons naming each legal representation of a
   union-typed field, in verbatim bpx.schema vocabulary. */
QToolButton#ModeButton {
    border: 1px solid #d0d7de; border-left-width: 0;
    padding: 3px 10px; background: #f6f8fa; color: #57606a; font-size: 11px;
}
QToolButton#ModeButton:first-child { border-left-width: 1px; border-top-left-radius: 4px; border-bottom-left-radius: 4px; }
QToolButton#ModeButton:last-child { border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
QToolButton#ModeButton:hover { background: #eef1f4; }
QToolButton#ModeButton:checked { background: #ffffff; color: #1f2328; font-weight: 600; border-bottom: 2px solid #1f6feb; }

/* Parameter-list pane's "+ Add parameter" header: a shaded, inset button
   rather than a native full-bleed one, and honestly greyed (not error-red)
   while disabled (no section selected). */
QPushButton#AddParameterButton {
    background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px;
    color: #1f2328; font-size: 12px; padding: 4px 8px;
}
QPushButton#AddParameterButton:hover:!disabled { background: #e8eaed; }
QPushButton#AddParameterButton:disabled {
    color: #8c959f; background: #f6f8fa; border: 1px solid #eaecef;
}

/* Add-parameter popup: a floating "command palette" surface. The frameless
   top-level is translucent; this rounded card carries the visible chrome so
   it reads like Raycast/Linear/VS Code Quick Open rather than a raw widget. */
QFrame#AddParameterCard {
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 10px;
}
QLineEdit#AddParameterInput {
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 6px 8px;
    background: #ffffff;
    font-size: 12px;
    selection-background-color: #ddeeff;
}
QLineEdit#AddParameterInput:focus { border: 1px solid #1f6feb; }
QLabel#AddParameterPopupHint { color: #57606a; padding: 2px 4px 4px 4px; }
QListWidget#AddParameterList {
    border: none;
    background: transparent;
    outline: none;
    font-size: 12px;
}
QListWidget#AddParameterList::item { padding: 8px; border-radius: 4px; }
QListWidget#AddParameterList::item:selected { background: #ddeeff; color: #1f2328; }
QFrame#AddParameterDivider { background: #eaecef; border: none; }
/* The pinned "Create custom parameter" action -- accent-tinted escape hatch,
   highlighted the same way as a selected row when keyboard focus reaches it. */
QPushButton#AddParameterCreate {
    text-align: left;
    padding: 8px 10px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: #1f6feb;
    font-weight: 500;
}
/* Same wash as the row-selected states above (style.ACCENT_TINT) -- this
   used to be its own near-identical #eaf2ff blue. */
QPushButton#AddParameterCreate:hover { background: #ddeeff; }
QPushButton#AddParameterCreate[selected="true"] { background: #ddeeff; }
"""
