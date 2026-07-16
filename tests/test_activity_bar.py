"""Activity bar icon rail, page header and Diagnostics severity badge.

Covers the activity bar's move from text buttons to icon-only buttons with
tooltip identity, the page header that names the active view, and the
Diagnostics badge's honesty about severity: a warnings-only document must
never show the error colour, and vice versa.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


# --- icon-only activity buttons ------------------------------------------


def test_activity_buttons_are_icon_only_with_tooltip_identity(app_driver):
    d = app_driver
    for label, btn in (
        ("Workspace", d._w._btn_workspace),
        ("Editor", d._w._btn_editor),
        ("Diagnostics", d._w._btn_diagnostics),
    ):
        assert btn.text() == ""
        assert not btn.icon().isNull()
        assert btn.accessibleName() == label
        # The Diagnostics tooltip carries severity detail beyond the bare
        # label once issues exist, so only assert equality for the two
        # buttons whose tooltip never changes.
        if label != "Diagnostics":
            assert btn.toolTip() == label


# --- page header tracks the active view -----------------------------------


def test_page_header_title_is_correct_on_first_show_with_no_document(app_driver):
    assert app_driver.page_header_title() == "Workspace"


def test_page_header_title_tracks_the_active_view(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)

    d.show_view("Editor")
    assert d.page_header_title() == "Editor"

    d.show_view("Diagnostics")
    assert d.page_header_title() == "Diagnostics"

    d.show_view("Workspace")
    assert d.page_header_title() == "Workspace"


# --- badge honesty ----------------------------------------------------------


def test_badge_is_clear_with_no_issues(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)

    assert app_driver.validation_badge_count() == 0
    assert app_driver.validation_badge_severity() is None
    assert app_driver.validation_tooltip() == "Diagnostics"


def test_badge_is_warning_only_for_a_warnings_only_document(app_driver, warning_only_bpx_path):
    d = app_driver
    d.open(warning_only_bpx_path)

    assert d.validation_badge_count() == 1
    assert d.validation_badge_severity() == "warning"
    assert d.validation_tooltip() == "Diagnostics — 1 warning"


def test_badge_is_error_when_any_error_exists(app_driver, invalid_bpx_path):
    d = app_driver
    d.open(invalid_bpx_path)

    assert d.validation_badge_count() > 0
    assert d.validation_badge_severity() == "error"


def test_badge_count_caps_display_at_99_plus(app_driver):
    btn = app_driver._w._btn_diagnostics
    btn.set_badge(150, "error")

    assert btn.badge_count == 150
    assert btn.badge_severity == "error"
    assert btn.badge_text() == "99+"


def test_badge_text_reflects_count(app_driver):
    btn = app_driver._w._btn_diagnostics

    btn.set_badge(0, None)
    assert btn.badge_text() == ""

    btn.set_badge(1, "warning")
    assert btn.badge_text() == "1"

    btn.set_badge(99, "warning")
    assert btn.badge_text() == "99"

    btn.set_badge(100, "error")
    assert btn.badge_text() == "99+"

    btn.set_badge(150, "error")
    assert btn.badge_text() == "99+"


# --- chrome actually paints (WA_StyledBackground) --------------------------
#
# ActivityBar and PageHeader are plain QWidget subclasses. Qt does not paint
# stylesheet ``background``/``border`` on a plain QWidget unless it opts in
# via ``setAttribute(Qt.WA_StyledBackground, True)`` -- without that call the
# rules in style.py are accepted but silently never drawn. These probes grab
# the real, styled widgets and check declared pixels directly, so a missing
# WA_StyledBackground call fails loudly instead of just looking "a bit off".


def test_activity_bar_paints_its_background_and_right_border(app_driver):
    bar = app_driver._w._activity_bar
    image = bar.grab().toImage()

    border_x = image.width() - 1
    probe_y = image.height() // 2
    border_pixel = image.pixelColor(border_x, probe_y).name()
    assert border_pixel == "#d0d7de", (
        f"ActivityBar right border pixel was {border_pixel}, not #d0d7de -- "
        "likely missing setAttribute(Qt.WA_StyledBackground, True) in "
        "ActivityBar.__init__, which silently drops all QSS background/"
        "border painting on a plain QWidget."
    )

    interior_pixel = image.pixelColor(10, probe_y).name()
    assert interior_pixel == "#f6f8fa", (
        f"ActivityBar interior pixel was {interior_pixel}, not #f6f8fa -- "
        "likely missing setAttribute(Qt.WA_StyledBackground, True) in "
        "ActivityBar.__init__, which silently drops all QSS background/"
        "border painting on a plain QWidget."
    )


def test_page_header_paints_its_background_and_bottom_border(app_driver):
    header = app_driver._w._page_header
    image = header.grab().toImage()

    border_y = image.height() - 1
    probe_x = image.width() // 2
    border_pixel = image.pixelColor(probe_x, border_y).name()
    assert border_pixel == "#d0d7de", (
        f"PageHeader bottom border pixel was {border_pixel}, not #d0d7de -- "
        "likely missing setAttribute(Qt.WA_StyledBackground, True) in "
        "PageHeader.__init__, which silently drops all QSS background/"
        "border painting on a plain QWidget."
    )

    interior_pixel = image.pixelColor(probe_x, 10).name()
    assert interior_pixel == "#ffffff", (
        f"PageHeader interior pixel was {interior_pixel}, not #ffffff -- "
        "likely missing setAttribute(Qt.WA_StyledBackground, True) in "
        "PageHeader.__init__, which silently drops all QSS background/"
        "border painting on a plain QWidget."
    )
