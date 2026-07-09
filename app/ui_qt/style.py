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
BORDER = "#d0d7de"
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
QLabel#CardTitle { font-size: 15px; font-weight: 600; }
QLabel#Heading { color: #57606a; font-weight: 600; }
QFrame#Card { border: 1px solid #d0d7de; }
QStatusBar { background: #f6f8fa; border-top: 1px solid #d0d7de; font-size: 12px; color: #57606a; }
QWidget#ActivityBar { background: #f6f8fa; border-right: 1px solid #d0d7de; }
QToolButton#ActivityButton {
    background: transparent; border: none; padding: 6px 4px;
    font-size: 12px; color: #57606a;
}
QToolButton#ActivityButton:checked {
    color: #1f2328; font-weight: 600;
    border-left: 3px solid #1f6feb; background: #eaf2ff;
}
QToolButton#ActivityButton:hover:!checked { background: #e8eaed; }
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
QLabel#IssuesPlaceholder { color: #57606a; font-size: 12px; padding: 16px; }

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
    selection-background-color: #ddeeff;
}
QLineEdit#AddParameterInput:focus { border: 1px solid #1f6feb; }
QLabel#AddParameterPopupHint { color: #57606a; padding: 2px 4px 4px 4px; }
QListWidget#AddParameterList {
    border: none;
    background: transparent;
    outline: none;
}
QListWidget#AddParameterList::item { padding: 6px 8px; border-radius: 6px; }
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
