"""Shared badge geometry and colour mapping (``ui_qt.badges``, unified badge
system Phase 2).

Cheap, no pixel comparisons -- just proves the one shared shape and the
severity->colour mapping both finishes are supposed to expose, per the
approved spec: height 15, full-pill radius, bold 10px text, 15px min-width,
5px horizontal padding.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from ui_qt import badges, style


# --- shared geometry --------------------------------------------------------


def test_badge_geometry_matches_the_approved_spec():
    assert badges.HEIGHT == 15
    assert badges.RADIUS == badges.HEIGHT // 2
    assert badges.FONT_PIXEL_SIZE == 10
    assert badges.MIN_WIDTH == 15
    assert badges.H_PADDING == 5


def test_badge_width_never_narrower_than_min_width(qapp):
    assert badges.badge_width("1") >= badges.MIN_WIDTH


def test_badge_width_grows_for_longer_text(qapp):
    assert badges.badge_width("99+") > badges.badge_width("1")


# --- severity -> colour mapping, both finishes ------------------------------


def test_tint_finish_maps_severities_to_style_colours():
    assert badges.badge_colors("error") == (style.ERROR_TINT, style.ERROR)
    assert badges.badge_colors("warning") == (style.WARNING_TINT, style.WARNING)
    assert badges.badge_colors(None) == (style.NEUTRAL_TINT, style.MUTED)


def test_solid_finish_maps_severities_to_style_colours_with_white_text():
    assert badges.badge_colors("error", solid=True) == (style.ERROR, "#ffffff")
    assert badges.badge_colors("warning", solid=True) == (style.WARNING, "#ffffff")
    assert badges.badge_colors(None, solid=True) == (style.MUTED, "#ffffff")


def test_unrecognised_severity_falls_back_to_the_neutral_tier():
    assert badges.badge_colors("bogus") == badges.badge_colors(None)
    assert badges.badge_colors("bogus", solid=True) == badges.badge_colors(None, solid=True)


# --- QLabel factory ----------------------------------------------------------


def test_make_badge_label_carries_the_shared_geometry(qtbot):
    label = badges.make_badge_label("3", style.ERROR_TINT, style.ERROR)
    qtbot.addWidget(label)

    assert label.text() == "3"
    assert label.height() == badges.HEIGHT
    assert label.minimumWidth() == badges.MIN_WIDTH
