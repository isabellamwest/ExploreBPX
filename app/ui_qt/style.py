"""Calm, information-dense palette and stylesheet for the desktop frontend.

A single global stylesheet keeps the look consistent (an IDE/XMLSpy feel)
rather than scattering ad-hoc styling across widgets. Colours are muted; accent
use is reserved for validity status only.
"""

from __future__ import annotations

OK = "#2e7d32"
ERROR = "#c62828"
WARNING = "#ef6c00"
ACCENT = "#1f6feb"
#: A required-but-absent/required-parameter tint -- distinct from both
#: ``ERROR`` (invalid) and ``ACCENT`` (a merely-suggested field), so a
#: schema-required parameter reads as its own, readable, amber category in
#: the add-parameter popup and the parameter list.
REQUIRED = "#9a6700"
BORDER = "#d0d7de"
#: Wash behind a grid cell the validator blamed -- a background tint, so it
#: reads distinctly from ``ERROR``, which is used as text/badge colour.
ERROR_TINT = "#ffebe9"
#: Muted/de-emphasised text. Used for secondary labels (e.g. QLabel#Heading)
#: and reused as the foreground for the add-parameter popup's "other BPX
#: alias" suggestion tier (aliases the section doesn't expect), so grey rows
#: draw from the same palette rather than a one-off colour.
MUTED = "#57606a"

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
/* Workspace page: the current-document card and its field rows. */
QFrame#DocInfoCard { border: 1px solid #d0d7de; border-radius: 6px; background: #f6f8fa; }
QLabel#DocInfoTitle { font-size: 15px; font-weight: 600; }
QLabel#DocInfoTitle:disabled { color: #8c959f; font-weight: 400; }
QLabel#DocInfoKey { color: #57606a; }
QLabel#NewChooserHeading { color: #57606a; font-weight: 600; }
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
/* The Validation page's single list. Borderless like the editor's flush
   panes (the activity bar and page header already draw the seams) and the
   same row rhythm as QListWidget#ParameterListView, so the two primary
   surfaces read as one system. */
QListWidget#ValidationList { border: none; }
QListWidget#ValidationList::item { padding: 6px 8px; border-radius: 4px; }
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
