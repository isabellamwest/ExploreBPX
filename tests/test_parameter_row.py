"""Tests for the shared rich-text row delegate (`ui_qt.parameter_row`), used
by both the add-parameter popup and the parameter-list pane."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QListWidget, QListWidgetItem

from ui_qt import style
from ui_qt.parameter_row import (
    HTML_ROLE,
    ParameterRowDelegate,
    build_parameter_row_html,
    compose_row_html,
    split_name_and_unit,
)


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
    html = build_parameter_row_html("Thickness [m]", has_errors=False)
    assert "Thickness" in html
    assert "[m]" in html
    assert f"color:{style.MUTED}" in html


def test_build_parameter_row_html_never_tints_a_row_by_requiredness():
    """Requiredness colouring is the add-parameter popup's language, for
    choosing a field that is not there yet. A row in this list is a parameter
    the document already has, so it is never tinted amber."""
    html = build_parameter_row_html("Thickness [m]", has_errors=False)
    assert f"color:{style.REQUIRED}" not in html


def test_build_parameter_row_html_error_marker_uses_error_colour():
    html = build_parameter_row_html("Thickness [m]", has_errors=True)
    assert f"color:{style.ERROR}" in html
    assert "⚠" in html  # the ⚠ marker


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
    short_html = build_parameter_row_html("Short [m]", has_errors=False)
    short_item = QListWidgetItem("Short [m]")
    short_item.setData(HTML_ROLE, short_html)
    rich_list.addItem(short_item)

    long_label = (
        "A very long parameter alias that will not possibly fit on a single "
        "line at the fixed width this test uses [m2.s-1]"
    )
    long_html = build_parameter_row_html(long_label, has_errors=False)
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
