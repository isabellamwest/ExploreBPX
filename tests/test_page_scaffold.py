"""cards/page.py: the Inspector page's shared header/content scaffold.

``page_content()``'s body is capped at ``style.PAGE_MEASURE`` -- the wider
measure that replaced ``style.CONTENT_MEASURE`` on this page once its
charts and grids (data surfaces, not prose) were found squeezed the exact
same way the Workspace page's cards once were. The Inspector's Issues/
Documentation sections (``ui_qt.inspector.InspectorPanel``) share the same
cap, for one right edge down the whole page -- see
``tests/test_workspace_panel.py`` for the Workspace page's own half of this
same measure.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from ui_qt import style
from ui_qt.cards.page import page_content


@pytest.fixture(autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def test_page_content_body_is_capped_at_the_shared_page_measure():
    body, _layout = page_content()

    assert body.maximumWidth() == style.PAGE_MEASURE


def test_page_measure_is_wider_than_the_prose_measure():
    """The whole point of the split: charts/grids/ledgers get more room
    than running prose should ever take."""
    assert style.PAGE_MEASURE > style.CONTENT_MEASURE


def test_inspector_issues_and_documentation_sections_share_the_page_measure(qtbot):
    """Both sit below the card, which now uses ``page_content()``'s own
    ``PAGE_MEASURE`` cap -- if these two kept the narrower
    ``CONTENT_MEASURE`` default, the page would show two different right
    edges."""
    from state.app_state import AppState
    from ui_qt.inspector import InspectorPanel

    panel = InspectorPanel(AppState())
    qtbot.addWidget(panel)

    assert panel._issues_section.body.maximumWidth() == style.PAGE_MEASURE
    assert panel._docs_section.body.maximumWidth() == style.PAGE_MEASURE
