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
QWidget#IssuesDrawer { background: #f6f8fa; border-left: 1px solid #d0d7de; }
QToolButton#IssuesToggle {
    background: #f6f8fa; border: none; border-bottom: 1px solid #d0d7de;
    padding: 5px 8px; font-size: 12px; color: #57606a; text-align: left;
}
QToolButton#IssuesToggle:hover { background: #e8eaed; }
QListWidget#IssuesList { border: none; background: #ffffff; font-size: 12px; }
"""
