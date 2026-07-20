"""Diagnostics page filters -- Phase B (F8, ``PLAN-completion-track.md`` S4b).

Filters are VIEW-ONLY (F8's core rule): rail badges, strip counts, the app
badge and F3 reconciliation always read the same unfiltered ``PageBuckets``
this module always has -- filtering only decides which rows the view
builders (``_SectionDetailView``/``_AllSectionsView``) actually add to their
lists. Every test here either proves a row disappears/reappears from a VIEW
while the TRUTH layer (buckets/badges/counts) stays untouched, or proves the
pure filter predicates (``_issue_visible``/``_task_visible``) directly.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

_CELL = ("Parameterisation", "Cell")


def _write(tmp_path, name: str, raw: dict):
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


@pytest.fixture
def two_cell_errors_path(tmp_path, valid_spm_dict):
    """Two distinct error rows in the Cell bucket, with distinguishable
    locations/messages so text-filter tests can target one but not the
    other."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "banana"
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = "low"
    return _write(tmp_path, "two_cell_errors.json", raw)


# ---------------------------------------------------------------------------
# Pure predicates (_FilterState / _issue_visible / _task_visible), no Qt
# widgets -- the "small pure filter helper" the view builders consume.
# ---------------------------------------------------------------------------


def test_issue_visible_matches_the_empty_location_placeholder():
    # A loc that collapses entirely into the bucket label displays
    # "(document)" (``_EMPTY_LOCATION_LABEL``); typing what the row shows
    # must match it -- regression for the display/haystack drift the
    # phase-B review caught.
    from core.validation import PydanticErrorDiagnostic, Severity
    from ui_qt.diagnostics_panel import _EMPTY_LOCATION_LABEL, _FilterState, _issue_visible

    diag = PydanticErrorDiagnostic(raw_error={"msg": "Value error, moved", "type": "value_error"}, severity=Severity.ERROR)
    empty_loc = ("Cell",)  # fully absorbed by the bucket label below

    assert _issue_visible(diag, empty_loc, "Cell", _FilterState(text="document")) is True
    assert _issue_visible(diag, empty_loc, "Cell", _FilterState(text=_EMPTY_LOCATION_LABEL)) is True
    assert _issue_visible(diag, empty_loc, "Cell", _FilterState(text="no-match-here")) is False


def test_issue_visible_respects_its_own_severity_chip_only():
    from core.validation import PydanticErrorDiagnostic, Severity
    from ui_qt.diagnostics_panel import _FilterState, _issue_visible

    error = PydanticErrorDiagnostic(raw_error={"msg": "bad", "type": "float_type"}, severity=Severity.ERROR)
    warning = PydanticErrorDiagnostic(raw_error={"msg": "meh", "type": "x"}, severity=Severity.WARNING)
    loc = ("Cell", "X")

    assert _issue_visible(error, loc, "Cell", _FilterState()) is True
    assert _issue_visible(error, loc, "Cell", _FilterState(error_on=False)) is False
    assert _issue_visible(warning, loc, "Cell", _FilterState(warning_on=False)) is False
    assert _issue_visible(warning, loc, "Cell", _FilterState(error_on=False)) is True


def test_issue_visible_text_filter_matches_location_or_message_case_insensitively():
    from core.validation import PydanticErrorDiagnostic, Severity
    from ui_qt.diagnostics_panel import _FilterState, _issue_visible

    diag = PydanticErrorDiagnostic(raw_error={"msg": "A Special Message", "type": "x"}, severity=Severity.ERROR)
    loc = ("Cell", "Thickness [m]")

    assert _issue_visible(diag, loc, "Cell", _FilterState(text="THICKNESS")) is True
    assert _issue_visible(diag, loc, "Cell", _FilterState(text="special")) is True
    assert _issue_visible(diag, loc, "Cell", _FilterState(text="no-match-here")) is False


def test_task_visible_respects_outstanding_chip_and_name_or_message_text():
    from core.completion import CompletionTask, TaskKind
    from ui_qt.diagnostics_panel import _FilterState, _task_visible

    task = CompletionTask(
        kind=TaskKind.MISSING_FIELD,
        path=("Parameterisation", "Cell", "Electrode area [m2]"),
        alias="Electrode area [m2]",
        required=True,
    )

    assert _task_visible(task, (), _FilterState()) is True
    assert _task_visible(task, (), _FilterState(outstanding_on=False)) is False
    assert _task_visible(task, (), _FilterState(text="electrode")) is True
    assert _task_visible(task, (), _FilterState(text="no-match")) is False
    assert _task_visible(task, ("Field required",), _FilterState(text="field required")) is True


# ---------------------------------------------------------------------------
# Chip filtering, end to end -- hides exactly the right category, in both
# the single-section pane and the All-sections view, leaving truth alone.
# ---------------------------------------------------------------------------


def test_error_chip_off_hides_error_rows_but_not_counts_or_badges(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_select_rail("Cell")
    assert len(d.diagnostics_section_issue_texts()) == 2
    assert d.diagnostics_chip_is_on("errors") is True

    d.diagnostics_toggle_chip("errors")

    assert d.diagnostics_chip_is_on("errors") is False
    assert d.diagnostics_section_issue_texts() == []
    assert d.validation_issue_texts() == []
    assert d.diagnostics_bucket("Cell").error_count == 2
    assert d.diagnostics_strip_counts()[0] == 2
    assert d.validation_badge_count() == 2


def test_outstanding_chip_off_hides_required_and_optional_task_rows(app_driver, tmp_path):
    from core import document_factory

    raw = document_factory.create("SPM", title="probe")
    raw["Parameterisation"]["Cell"]["Volume [m3]"] = None
    d = app_driver
    d.open(_write(tmp_path, "cell_with_optional.json", raw))
    d.diagnostics_select_rail("Cell")
    assert len(d.diagnostics_section_task_texts()) == 6  # 5 required + 1 optional, both "task" rows
    assert len(d.diagnostics_section_optional_subhead_texts()) == 1

    d.diagnostics_toggle_chip("outstanding")

    assert d.diagnostics_section_task_texts() == []
    assert d.diagnostics_section_optional_subhead_texts() == []
    bucket = d.diagnostics_bucket("Cell")
    assert bucket.outstanding_count == 6


def test_chip_toggle_never_changes_the_rail_badge_or_strip(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    before = d.diagnostics_strip_counts()
    rail_before = {label: d.diagnostics_bucket(label) for label in d.diagnostics_rail_labels()[1:]}

    d.diagnostics_toggle_chip("errors")
    d.diagnostics_toggle_chip("warnings")
    d.diagnostics_toggle_chip("outstanding")

    assert d.diagnostics_strip_counts() == before
    for label, bucket_before in rail_before.items():
        bucket_after = d.diagnostics_bucket(label)
        assert (bucket_after.error_count, bucket_after.warning_count, bucket_after.outstanding_count) == (
            bucket_before.error_count,
            bucket_before.warning_count,
            bucket_before.outstanding_count,
        )


# ---------------------------------------------------------------------------
# Text filter, end to end.
# ---------------------------------------------------------------------------


def test_text_filter_matches_case_insensitively_and_updates_live(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_select_rail("Cell")

    d.diagnostics_set_filter_text("LOWER")

    texts = d.diagnostics_section_issue_texts()
    assert len(texts) == 1
    assert "Lower voltage" in texts[0]


def test_text_filter_matches_message_text(app_driver, tmp_path, valid_spm_dict):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Positive electrode"]["Diffusivity [m2.s-1]"] = "fast"
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "banana"
    d = app_driver
    d.open(_write(tmp_path, "message_filter.json", raw))

    d.diagnostics_set_filter_text("not permitted")

    texts = d.validation_issue_texts()
    assert len(texts) == 1
    assert "Diffusivity" in texts[0]


def test_escape_clears_the_filter_field(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_select_rail("Cell")
    d.diagnostics_set_filter_text("lower")
    assert len(d.diagnostics_section_issue_texts()) == 1

    d.diagnostics_press_escape_in_filter()

    assert d.diagnostics_filter_text() == ""
    assert len(d.diagnostics_section_issue_texts()) == 2


def test_text_filter_composes_with_chips_as_and(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_select_rail("Cell")

    d.diagnostics_toggle_chip("errors")
    d.diagnostics_set_filter_text("lower")

    assert d.diagnostics_section_issue_texts() == []


# ---------------------------------------------------------------------------
# "N hidden by filters" -- present with the right N, absent when nothing is
# hidden, and never mistakable for (or co-rendered with) a pinned check
# state.
# ---------------------------------------------------------------------------


def test_hidden_line_absent_by_default_and_present_after_a_toggle(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_select_rail("Cell")
    assert d.diagnostics_section_hidden_line_text() is None

    d.diagnostics_toggle_chip("errors")
    assert d.diagnostics_section_hidden_line_text() == "2 hidden by filters"

    d.diagnostics_toggle_chip("errors")
    assert d.diagnostics_section_hidden_line_text() is None


def test_pinned_empty_state_never_co_renders_with_the_hidden_line(app_driver):
    d = app_driver
    d._w._new("SPM")
    d.diagnostics_select_rail("Cell")
    assert d.diagnostics_section_issues_empty_text() == "✓ No issues"
    assert d.diagnostics_section_outstanding_empty_text() is None

    d.diagnostics_toggle_chip("outstanding")

    assert d.diagnostics_section_issues_empty_text() == "✓ No issues"
    assert d.diagnostics_section_outstanding_empty_text() is None
    assert d.diagnostics_section_hidden_line_text() == "5 hidden by filters"


def test_all_sections_hidden_line_reflects_document_wide_count(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    assert d.diagnostics_all_sections_hidden_line_text() is None

    d.diagnostics_toggle_chip("errors")

    assert d.diagnostics_all_sections_hidden_line_text() == "2 hidden by filters"


# ---------------------------------------------------------------------------
# Fold state composes independently of filters (F8): a fold-hidden row is
# never counted in "N hidden by filters".
# ---------------------------------------------------------------------------


def test_fold_hidden_rows_are_excluded_from_the_hidden_count(app_driver):
    d = app_driver
    d._w._new("SPM")
    d.diagnostics_toggle_chip("outstanding")
    # bpx 1.1.1: `State` is schema-optional and no longer scaffolded by a new
    # document (see core.document_factory), so its two former task rows are
    # gone -- 23, not 25.
    assert d.diagnostics_all_sections_hidden_line_text() == "23 hidden by filters"

    d.toggle_all_sections_fold("Cell")

    assert d.diagnostics_all_sections_hidden_line_text() == "18 hidden by filters"


# ---------------------------------------------------------------------------
# Persistence: like rail selection, filter state survives an ordinary
# refresh and resets only for a different document (F6/F8).
# ---------------------------------------------------------------------------


def test_filter_state_persists_across_a_commit_triggered_refresh(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_toggle_chip("errors")
    d.diagnostics_set_filter_text("lower")

    d._w._state.active.apply_value(("Parameterisation", "Cell", "Volume [m3]"), 1.0)
    d._w._refresh_all()

    assert d.diagnostics_chip_is_on("errors") is False
    assert d.diagnostics_filter_text() == "lower"


def test_filter_state_resets_on_a_new_document(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_toggle_chip("errors")
    d.diagnostics_set_filter_text("lower")

    d._w._state.active.dirty = False
    d._w._new("SPM")

    assert d.diagnostics_chip_is_on("errors") is True
    assert d.diagnostics_chip_is_on("warnings") is True
    assert d.diagnostics_chip_is_on("outstanding") is True
    assert d.diagnostics_filter_text() == ""


# ---------------------------------------------------------------------------
# Activation still works on visible rows while filters are active.
# ---------------------------------------------------------------------------


def test_activation_navigates_to_the_correct_visible_parameter_while_filtered(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_set_filter_text("lower")

    visible = d._validation_rows("issue")
    assert len(visible) == 1
    d.activate_validation_row(visible[0])

    assert d.inspector_title() == "Lower voltage cut-off [V]"


# ---------------------------------------------------------------------------
# F3 note: with every chip off, the truth layer (buckets/badges) must still
# fully reconcile -- it never saw the filter at all.
# ---------------------------------------------------------------------------


def test_all_chips_off_buckets_and_badges_still_reconcile(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    errors, warnings, outstanding = d.diagnostics_strip_counts()
    app_badge = d.validation_badge_count()
    app_severity = d.validation_badge_severity()

    d.diagnostics_toggle_chip("errors")
    d.diagnostics_toggle_chip("warnings")
    d.diagnostics_toggle_chip("outstanding")
    d.diagnostics_set_filter_text("this matches nothing at all")

    assert d._validation_rows("issue") == []
    assert d._validation_rows("task") == []
    assert d.diagnostics_strip_counts() == (errors, warnings, outstanding)
    assert d.validation_badge_count() == app_badge
    assert d.validation_badge_severity() == app_severity


def test_chip_toggles_on_left_click_only(qtbot):
    # Review hardening: a right/middle click must not silently flip a
    # filter -- only the left button toggles.
    from PySide6.QtCore import Qt
    from ui_qt.diagnostics_panel import _FilterChip

    chip = _FilterChip()
    qtbot.addWidget(chip)
    assert chip.is_on()

    qtbot.mouseClick(chip, Qt.RightButton)
    assert chip.is_on()
    qtbot.mouseClick(chip, Qt.MiddleButton)
    assert chip.is_on()
    qtbot.mouseClick(chip, Qt.LeftButton)
    assert not chip.is_on()
