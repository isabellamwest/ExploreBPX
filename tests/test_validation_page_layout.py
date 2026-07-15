"""Validation page — Concept A layout (2026-07-15 design pass).

Issues cluster into collapsible section groups; each issue row splits its
location (bold) from the validator's message (muted, second line); the page
headers carry a muted count suffix. Companion fix landed with this pass: a
bad *string* in a FloatInt field (float_parsing + int_parsing) now merges to
one displayed row, like the null/wrong-type pair (decision Q), so its badge
count and its rows agree.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from ui_qt.validation_panel import _MSG_NO_ISSUES, ValidationPanel

_CELL = ("Parameterisation", "Cell")


def _write(tmp_path, name: str, raw: dict):
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


@pytest.fixture
def many_issues_path(tmp_path, valid_spm_dict):
    """A document with errors spread across three sections + one absorbed
    null, so the section grouping and counts have something to show."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "banana"
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = "low"
    raw["Parameterisation"]["Negative electrode"]["Thickness [m]"] = "thin"
    raw["Parameterisation"]["Positive electrode"]["Diffusivity [m2.s-1]"] = "fast"
    return _write(tmp_path, "many_issues.json", raw)


# --- the pure count-suffix helpers --------------------------------------


class _P:  # minimal PartitionedIssues stand-in for the pure suffix helpers
    def __init__(self, e, w):
        self.error_count, self.warning_count = e, w


def test_issues_count_suffix_wording():
    assert ValidationPanel._issues_count_suffix(_P(0, 0)) == ""
    assert ValidationPanel._issues_count_suffix(_P(1, 0)) == "  ·  1 error"
    assert ValidationPanel._issues_count_suffix(_P(4, 0)) == "  ·  4 errors"
    assert ValidationPanel._issues_count_suffix(_P(2, 1)) == "  ·  2 errors · 1 warning"


def test_outstanding_count_suffix_wording():
    assert ValidationPanel._outstanding_count_suffix(()) == ""
    assert ValidationPanel._outstanding_count_suffix((object(),)) == "  ·  1 remaining"


# --- section grouping ----------------------------------------------------


def test_issues_are_grouped_by_section(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    groups = d.validation_section_groups()
    sections = [name for name, _collapsed in groups]
    assert sections == ["Cell", "Negative electrode", "Positive electrode"]
    assert all(not collapsed for _name, collapsed in groups)


def test_bad_string_floatint_shows_one_row_not_two(app_driver, many_issues_path):
    """The float_parsing+int_parsing merge (companion fix): one problem, one
    row, and the badge counts it once."""
    d = app_driver
    d.open(many_issues_path)
    # 4 sections mutated -> 4 errors, each a single merged row (not 7).
    assert d.validation_badge_count() == 4
    assert len(d.validation_issue_texts()) == 4
    # No "valid integer" wording survives the merge.
    assert not any("valid integer" in text for text in d.validation_issue_texts())


def test_issue_row_splits_location_from_message(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    html = d.validation_issue_html()
    row = next(h for h in html if "Lower voltage cut-off" in h)
    # location and message are on two lines (a <br> between them); the unit
    # is muted, the message present.
    assert "<br>" in row
    assert "Lower voltage cut-off" in row
    assert "[V]" in row
    assert "Input should be a valid number" in row
    # the section prefix is dropped -- it's the group header, not the row.
    assert "Cell" not in row.split("<br>")[0]


# --- collapse ------------------------------------------------------------


def test_collapsing_a_section_hides_its_issue_rows(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    before = len(d.validation_issue_texts())
    d.toggle_validation_section("Cell")

    groups = dict(d.validation_section_groups())
    assert groups["Cell"] is True  # collapsed
    # Cell held 2 issues; folding removes exactly those rows.
    assert len(d.validation_issue_texts()) == before - 2
    # other groups stay open
    assert groups["Negative electrode"] is False


def test_collapse_survives_a_refresh(app_driver, many_issues_path, tmp_path, valid_spm_dict):
    """Folding a section must not snap open on the next commit/refresh."""
    d = app_driver
    d.open(many_issues_path)
    d.toggle_validation_section("Cell")
    assert dict(d.validation_section_groups())["Cell"] is True

    # An unrelated edit triggers a full refresh of the panel.
    d._w.navigate_to(_CELL)
    d._w._state.active.apply_value(
        ("Parameterisation", "Cell", "Volume [m3]"), 1.0
    )
    d._w._refresh_all()

    assert dict(d.validation_section_groups())["Cell"] is True


# --- clean document ------------------------------------------------------


def test_clean_document_has_no_groups_or_counts(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)
    assert d.validation_section_groups() == []
    assert d.validation_issues_empty_text() == _MSG_NO_ISSUES
    # Page header text stays the bare title (no count suffix) when clean.
    assert d.validation_page_headers() == ["Issues", "Outstanding"]
