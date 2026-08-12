"""Tests for the shared rich-text row delegate (`ui_qt.parameter_row`), used
by both the add-parameter popup and the parameter-list pane."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem

from ui_qt import icons, style, typography
from ui_qt.parameter_row import (
    HTML_ROLE,
    MARK_BOX,
    REF_BAR_ROLE,
    ParameterRowDelegate,
    build_parameter_row_html,
    cap_midline_mark_top,
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


def test_a_detail_suffix_joins_the_message_with_the_app_separator():
    """*detail* (e.g. the offending value) lands after *message* on the
    same line, in the same muted-message span -- never a separate line or
    a different colour -- joined with the app's " · " middle-dot
    separator, and the verbatim message text survives unchanged."""
    html = compose_issue_row_html("Thickness [m]", "value must be positive", "input -0.3")
    assert "value must be positive · input -0.3" in html
    assert html.count("<br>") == 1  # still just location/message, one split


def test_no_detail_omits_the_suffix_entirely():
    html_with_none = compose_issue_row_html("Thickness [m]", "value must be positive", None)
    html_without = compose_issue_row_html("Thickness [m]", "value must be positive")
    assert html_with_none == html_without
    assert "·" not in html_without


# ---------------------------------------------------------------------------
# cap_midline_mark_top -- the shared mark-alignment helper (pure QFontMetrics
# maths, no painting, so these are offscreen-safe like every other test here).
# ---------------------------------------------------------------------------


def test_cap_midline_mark_top_centres_the_mark_on_the_cap_midline():
    """The returned top, plus half the mark size, must land exactly on the
    cap midline: the vertically-centred-text baseline (text_rect's own
    formula) minus half the font's cap height -- the same "riding low
    against a capital letter's optical centre" fix ``tree_panel`` used to
    compute inline, now shared."""
    font = QFont()
    font.setPixelSize(13)
    metrics = QFontMetrics(font)
    text_rect = QRect(0, 100, 200, 20)
    mark_size = 13

    top = cap_midline_mark_top(text_rect, metrics, mark_size)

    baseline = text_rect.y() + (text_rect.height() + metrics.ascent() - metrics.descent()) / 2
    expected_midline = baseline - metrics.capHeight() / 2
    assert abs((top + mark_size / 2) - expected_midline) <= 0.5


def test_cap_midline_mark_top_matches_tree_panels_original_inline_formula():
    """Regression guard for promoting this out of ``_TreeItemDelegate.paint``:
    reproduces that exact original expression (integer baseline via ``//``,
    matching Qt's own text-centring maths) so the extraction changed no
    behaviour, down to the rounding."""
    font = QFont()
    font.setPixelSize(13)
    metrics = QFontMetrics(font)
    text_rect = QRect(5, 40, 150, 22)
    mark_size = MARK_BOX

    baseline = text_rect.y() + (text_rect.height() + metrics.ascent() - metrics.descent()) // 2
    expected = round(baseline - metrics.capHeight() / 2 - mark_size / 2)

    assert cap_midline_mark_top(text_rect, metrics, mark_size) == expected


def test_cap_midline_mark_top_is_independent_of_text_rect_x_and_width():
    """Only the vertical geometry (y, height) and the font feed the
    formula -- x/width are irrelevant, matching how callers pass a text
    rect whose width varies with the label text beside the mark."""
    font = QFont()
    font.setPixelSize(11)
    metrics = QFontMetrics(font)
    narrow = QRect(0, 50, 10, 18)
    wide = QRect(999, 50, 500, 18)

    assert cap_midline_mark_top(narrow, metrics, 13) == cap_midline_mark_top(wide, metrics, 13)


# ---------------------------------------------------------------------------
# icons._default_inline_lift -- the derived (not hand-tuned) replacement for
# the old flat _INLINE_LIFT = 2.
# ---------------------------------------------------------------------------


def test_default_inline_lift_matches_body_font_cap_x_height_gap():
    """Derived, not hand-tuned: half the gap between the BODY UI font's cap
    height and x-height, rounded -- not a bare literal."""
    metrics = QFontMetrics(typography.ui_font(typography.BODY))
    expected = round((metrics.capHeight() - metrics.xHeight()) / 2)
    assert icons._default_inline_lift() == expected


def test_html_img_explicit_lift_overrides_the_derived_default():
    """A call site whose adjacent text is not BODY (e.g. a card header's
    isolated dot beside META badge text) can override the derived default;
    the two renders must differ, and each must cache under its own key."""
    default_html = icons.html_img(icons.DOT, color=style.ERROR, size=13)
    overridden_html = icons.html_img(icons.DOT, color=style.ERROR, size=13, lift=0)
    if icons._default_inline_lift() != 0:
        assert default_html != overridden_html
