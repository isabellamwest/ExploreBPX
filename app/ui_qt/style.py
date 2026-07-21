"""Calm, information-dense palette and stylesheet for the desktop frontend.

A single global stylesheet keeps the look consistent (an IDE/XMLSpy feel)
rather than scattering ad-hoc styling across widgets. Colours are muted; accent
use is reserved for validity status only.
"""

from __future__ import annotations

from core.completion import TaskKind
from core.validation import Severity

OK = "#2e7d32"
ERROR = "#c62828"
WARNING = "#ef6c00"
ACCENT = "#1f6feb"
#: The reference-file feature's own accent: purple, by explicit user
#: decision -- everything reference-specific carries this one hue so it is
#: visually unmistakable, and it can never be confused with ``ACCENT`` (the
#: app's general blue) or any severity colour. Used by the Workspace
#: reference card's tag (M1); ghost rows/sections (a later milestone) are
#: expected to reuse it.
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
#: Warning-badge background (Diagnostics page rail redesign, F5) -- the
#: ``WARNING`` counterpart to ``ERROR_TINT``.
WARNING_TINT = "#fff1e0"
#: Neutral grey badge background: the "All sections" rail entry's total
#: badge and every "outstanding" count badge (rail/pane), which are never
#: red/amber -- decision B's "outstanding is not an error" kept visible in
#: the colour itself.
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
#: Diagnostics page rail (F2): background distinct from the white detail
#: pane, and the selected entry's accent-tinted background/hover wash.
RAIL_BG = "#f3f4f6"
RAIL_SELECTED_BG = "#e3edfd"
RAIL_HOVER_BG = "#e8eaed"
#: Crisper-boxes polish round: one step darker than the app's usual
#: ``#d0d7de``/``#d9dee5`` border tones, used only on the Diagnostics page's
#: own chrome (group-box border, rail's right edge, strip's bottom edge,
#: chip borders) so those regions read a touch more defined without raising
#: contrast anywhere else in the app. Fills/palette are otherwise unchanged
#: -- flat colour only, no shadows.
BORDER_STRONG = "#c4cdd5"
#: Slightly stronger shaded band for the Diagnostics group-box header row --
#: one step darker than the app's usual ``#f6f8fa`` banded-header tone.
HEADER_BAND_STRONG = "#eef1f4"

# ---------------------------------------------------------------------------
# Tooltip vocabulary (F5 polish round): the app's four completion/severity
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


def all_clear(text: str) -> str:
    """Prefix *text* with the app's one "all clear" glyph (a plain check),
    used by every "nothing outstanding" empty-row message (Diagnostics'
    Issues/Outstanding lists, the Inspector's Issues tab) so the three
    surfaces never drift onto their own check-mark spelling."""
    return "✓ " + text


def validity_pill_qss(background: str) -> str:
    """Inline stylesheet for a document-validity pill (white text on
    *background*) -- shared by the parameter card's per-card badge and the
    workspace panel's document-info badge, which used to each hand-roll a
    slightly different padding."""
    return f"color: white; background: {background}; padding: 2px 9px; border-radius: 3px;"


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
QTreeView, QListWidget { border: 1px solid #d0d7de; background: #ffffff; }
QTreeView::item, QListWidget::item { padding: 3px 4px; }
QListWidget::item:selected, QTreeView::item:selected { background: #ddeeff; color: #1f2328; }
/* Editor page: the tree and parameter-list panes sit flush against the
   splitter's own 1px hairline (see QSplitter#EditorSplitter::handle below),
   so their own borders are stripped to avoid a doubled seam. Explicit ids
   only -- a descendant selector here would out-specify (and silently strip
   the border from) QListWidget#AddParameterList below. */
QTreeView#StructureTree, QListWidget#ParameterListView { border: none; }
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
QLabel#Heading { color: #57606a; font-weight: 600; }
QLabel#CardDescription { color: #57606a; padding-top: 4px; }
QFrame#Card { border: 1px solid #d0d7de; }
/* Workspace page (Concept A revised, signed off): a canvas one step darker
   than the app chrome, with one shared white-card treatment for the three
   regions (actions, current document, reference) -- the same surface
   inversion the Diagnostics page already uses (shaded rail, white pane).
   The document and reference cards share the full anatomy (title row,
   validity pill, key/value rows); the reference card carries the feature's
   purple (style.REFERENCE) as a very subtle fill/border tint plus its
   heading and the small Read-only tag -- never louder than the document
   card (no bar, no caps). */
QWidget#WorkspacePage { background: #eef1f4; }
QFrame#WorkspaceCard { background: #ffffff; border: 1px solid #c4cdd5; border-radius: 6px; }
QFrame#ReferenceCard { background: #fbfafe; border: 1px solid #d5cde6; border-radius: 6px; }
QLabel#WorkspaceCardTitle { font-size: 15px; font-weight: 600; }
QLabel#WorkspaceCardTitle:disabled { color: #8c959f; font-weight: 400; }
QLabel#WorkspaceCardKey { color: #57606a; }
QLabel#NewChooserHeading { color: #57606a; font-weight: 600; }
QLabel#ReferenceHeading { color: #7a63ad; font-weight: 600; }
QLabel#ReferenceReadOnlyTag { color: #6f42c1; font-size: 11px; font-weight: 600; margin-top: 3px; }
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
QListWidget#SearchPopupList::item { padding: 6px 8px; border-radius: 6px; }
QListWidget#SearchPopupList::item:selected { background: #ddeeff; color: #1f2328; }
/* The Diagnostics page (rail redesign, F2): a summary strip over a
   fixed-width rail beside a detail pane. The rail's own background is
   distinct from the white pane so the two read as separate surfaces, like
   the activity bar beside the editor. Crisper-boxes polish round: the
   strip/rail/group-box/chip border lines use BORDER_STRONG (#c4cdd5), one
   step darker than the app's usual #d0d7de/#d9dee5, so this page's own
   regions read a touch more defined -- flat colour only, no shadows, and
   nothing outside this page's chrome changed. */
QWidget#DiagnosticsSummaryStrip { background: #f9fafb; border-bottom: 1px solid #c4cdd5; }
/* One strip chip (F2 wireframe: "boxes/shading to make regions
   distinguishable") -- a small bordered, rounded card on the shaded strip
   band, distinct from the flat text it replaced. F8: each chip is now a
   click-toggle filter; its "off" state is a dynamic QSS property
   (chipOff="true", set via setProperty + style().polish(), the same
   pattern QPushButton#AddParameterCreate's own "selected" property already
   uses below) -- a visibly muted/pressed-out card, never a hidden one
   (toggling never removes the chip itself, only what it filters). */
QLabel#DiagnosticsChip {
    background: #ffffff; border: 1px solid #c4cdd5; border-radius: 6px; padding: 4px 10px;
}
QLabel#DiagnosticsChip[chipOff="true"] { background: #eef0f2; border: 1px solid #d9dee5; }
QListWidget#DiagnosticsRail { background: #f3f4f6; border: none; border-right: 1px solid #c4cdd5; outline: none; }
QListWidget#DiagnosticsRail::item { padding: 0; border: none; }
QLabel#DiagnosticsPaneHeader { font-size: 14px; padding-bottom: 2px; }
/* F8's "N hidden by filters" line -- quiet, muted, never mistakable for a
   pinned empty-state (those use the shared muted-message row colour too,
   but this one only ever appears alongside real, still-counted rows). */
QLabel#DiagnosticsHiddenLine { color: #57606a; font-size: 12px; padding: 2px 2px; }
/* One F2 group box: a bordered, rounded card with a shaded, banded header
   row -- the same "IDE panel" language as QFrame#Card elsewhere. The header
   band uses HEADER_BAND_STRONG (#eef1f4), one step darker than the app's
   usual #f6f8fa banded-header tone. */
QFrame#DiagnosticsGroupBox { background: #ffffff; border: 1px solid #c4cdd5; border-radius: 6px; }
QWidget#DiagnosticsGroupBoxHeader {
    background: #eef1f4; border-bottom: 1px solid #c4cdd5;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QLabel#DiagnosticsGroupBoxTitle { font-weight: 600; }
QListWidget#DiagnosticsGroupBoxList { border: none; background: transparent; }
QListWidget#DiagnosticsGroupBoxList::item { padding: 6px 8px; border-radius: 4px; }
QListWidget#DiagnosticsGroupBoxList::item:hover { background: #f0f2f4; }
QListWidget#DiagnosticsGroupBoxList::item:selected { background: #ddeeff; color: #1f2328; }
/* "All sections", the F3 backup view: one continuous list, same row rhythm
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
    color: #8c959f; background: #f6f8fa; border: 1px solid #e1e4e8;
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
    border-radius: 6px;
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
QListWidget#AddParameterList::item { padding: 8px; border-radius: 6px; }
QListWidget#AddParameterList::item:selected { background: #ddeeff; color: #1f2328; }
QFrame#AddParameterDivider { background: #eaecef; border: none; }
/* The pinned "Create custom parameter" action -- accent-tinted escape hatch,
   highlighted the same way as a selected row when keyboard focus reaches it. */
QPushButton#AddParameterCreate {
    text-align: left;
    padding: 8px 10px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #1f6feb;
    font-weight: 500;
}
QPushButton#AddParameterCreate:hover { background: #eaf2ff; }
QPushButton#AddParameterCreate[selected="true"] { background: #ddeeff; }
"""
