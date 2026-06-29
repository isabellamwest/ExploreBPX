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
QFrame#IssuesPane { border: 1px solid #d0d7de; background: #f6f8fa; }
QStatusBar { background: #f6f8fa; border-top: 1px solid #d0d7de; }
"""
