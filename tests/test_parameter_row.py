"""Tests for the shared rich-text row delegate (`ui_qt.parameter_row`), used
by both the add-parameter popup and the parameter-list pane."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem

from ui_qt import icons, style, typography
from ui_qt.parameter_row import (
    HTML_ROLE,
    MARK_BOX,
    REF_BAR_ROLE,
    ParameterRowDelegate,
    build_parameter_row_html,
    compose_issue_row_html,
    compose_row_html,
    split_name_and_unit,
)


@pytest.fixture(autouse=True)
def _qapp():
    """A severity dot renders via ``icons.html_img`` (a real ``QPixmap``),
    so even the plain-function tests below need a live ``QApplication``."""
    yield QApplication.instance() or QApplication([])


def test_split_name_and_unit_strips_trailing_bracket():
    assert split_name_and_unit("Thickness [m]") == ("Thickness", "m")


def test_split_name_and_unit_passes_through_a_unitless_label():
    label = "Number of electrode pairs connected in parallel to make a cell"
    assert split_name_and_unit(label) == (label, "")


def test_compose_row_html_colours_name_and_hints():
    html = compose_row_html("Density", [("FloatInt", style.MUTED)], name_color=style.ACCENT)
    assert f"color:{style.ACCENT}" in html
    assert f"color:{style.MUTED}" in html
    assert "Density" in html
    assert "FloatInt" in html


def test_build_parameter_row_html_bolds_the_name_and_mutes_the_unit():
    html = build_parameter_row_html("Thickness [m]", severity=None)
    assert "Thickness" in html
    assert "[m]" in html
    assert f"color:{style.MUTED}" in html


def test_build_parameter_row_html_never_tints_a_row_by_requiredness():
    """Requiredness colouring is the add-parameter popup's language, for
    choosing a field that is not there yet. A row in this list is a parameter
    the document already has, so it is never tinted amber."""
    html = build_parameter_row_html("Thickness [m]", severity=None)
    assert f"color:{style.REQUIRED}" not in html


def test_build_parameter_row_html_error_marker_uses_error_colour():
    """An error row's trailing dot is the shared DOT mark rendered in
    ``style.ERROR`` -- no more literal ``⚠`` text."""
    html = build_parameter_row_html("Thickness [m]", severity="error")
    assert icons.html_img(icons.DOT, color=style.ERROR, size=MARK_BOX) in html
    assert "⚠" not in html


def test_build_parameter_row_html_warning_marker_uses_warning_colour():
    """A warnings-only row's dot is amber, not red -- the severity
    distinction the wireframe calls for."""
    html = build_parameter_row_html("Thickness [m]", severity="warning")
    assert icons.html_img(icons.DOT, color=style.WARNING, size=MARK_BOX) in html
    assert icons.html_img(icons.DOT, color=style.ERROR, size=MARK_BOX) not in html


def test_build_parameter_row_html_no_severity_has_no_dot():
    html = build_parameter_row_html("Thickness [m]", severity=None)
    assert "<img" not in html


@pytest.fixture
def rich_list(qtbot):
    lst = QListWidget()
    lst.setWordWrap(True)
    lst.setFixedWidth(240)
    lst.setItemDelegate(ParameterRowDelegate(lst))
    qtbot.addWidget(lst)
    lst.show()
    return lst


def test_wrapped_row_size_hint_grows_for_a_long_alias(rich_list):
    """A long alias wraps onto extra lines (word wrap, no eliding) instead of
    being clipped to one line, so its row grows taller than a short one."""
    short_html = build_parameter_row_html("Short [m]", severity=None)
    short_item = QListWidgetItem("Short [m]")
    short_item.setData(HTML_ROLE, short_html)
    rich_list.addItem(short_item)

    long_label = (
        "A very long parameter alias that will not possibly fit on a single "
        "line at the fixed width this test uses [m2.s-1]"
    )
    long_html = build_parameter_row_html(long_label, severity=None)
    long_item = QListWidgetItem(long_label)
    long_item.setData(HTML_ROLE, long_html)
    rich_list.addItem(long_item)

    short_height = rich_list.sizeHintForRow(0)
    long_height = rich_list.sizeHintForRow(1)
    assert long_height > short_height


def test_row_without_html_role_falls_back_to_plain_rendering(rich_list):
    """A row with no ``HTML_ROLE`` data (e.g. a popup group header) is left
    entirely to the base ``QStyledItemDelegate`` -- must not raise, and still
    reports a sane height."""
    plain = QListWidgetItem("A header row")
    rich_list.addItem(plain)
    assert rich_list.sizeHintForRow(0) > 0


def test_ref_bar_role_actually_paints_the_gutter_bar(rich_list, qtbot):
    """``REF_BAR_ROLE`` must produce real painted pixels, not just item data
    a headless test can read back.

    A styled ``QListWidget::item`` (this app's global stylesheet declares
    one) silently ignores ``QListWidgetItem.setBackground``'s
    ``Qt.BackgroundRole`` -- a genuine Qt/QSS gotcha caught only by grabbing
    the actual rendered pixmap (an offscreen-suite-misses-native-window-bugs
    case, the project guide); reading the item's own data back would have looked
    correct while painting nothing at all.
    """
    item = QListWidgetItem("Differing row")
    item.setData(HTML_ROLE, build_parameter_row_html("Differing row", severity=None))
    item.setData(REF_BAR_ROLE, "differs")
    rich_list.addItem(item)
    rich_list.show()
    qtbot.waitExposed(rich_list)

    image = rich_list.viewport().grab().toImage()
    # The bar occupies the row's left 3px, inset 4px from top/bottom; its
    # interior pixels carry the solid reference purple exactly.
    colours = {
        image.pixelColor(x, y).name()
        for x in range(0, 3)
        for y in range(0, min(30, image.height()))
    }
    assert style.REFERENCE in colours


def test_a_located_issue_row_keeps_its_message_as_a_smaller_second_line():
    html = compose_issue_row_html("Thickness [m]", "value must be positive")
    assert "<br>" in html
    assert typography.size_qss(typography.META) in html


def test_a_message_only_issue_row_is_body_text_not_a_footnote():
    """With no location the message *is* the row (a document-level
    diagnostic, or the Issues tab). Muted META is the right weight for a
    second line under a heading; as the only line it made the page's
    content read as a footnote."""
    html = compose_issue_row_html("", "value must be positive")
    assert typography.size_qss(typography.META) not in html
    assert style.MUTED not in html
    assert style.DEFAULT_TEXT in html
