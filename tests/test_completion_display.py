"""Driver-level tests for the completion track, through the real ``MainWindow``.

Covers: the null-field result matrix (required-expected / optional-expected /
custom), absorbed validator messages surfacing as Outstanding secondary text,
the float_type+int_type union-pair display merge in the Issues tab, the
page's Issues section and the badge, and the value-removed flow end to end
(fill -> commit -> null -> commit).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from core.completion import TaskKind

_CELL = ("Parameterisation", "Cell")
_LOWER_CUTOFF = _CELL + ("Lower voltage cut-off [V]",)


def _write(tmp_path, name: str, raw: dict):
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The result matrix: required-expected null, optional-expected null, custom
# null, filled-bad, filled-valid.
# ---------------------------------------------------------------------------


def test_required_expected_null_is_grey_without_warning(app_driver, tmp_path, valid_spm_dict):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = None
    d = app_driver
    d.open(_write(tmp_path, "required_null.json", raw))
    d.select_object(_CELL)
    d.diagnostics_select_rail("Cell")

    assert d.parameter_row_is_grey("Lower voltage cut-off [V]")
    assert not d.parameter_row_has_warning_marker("Lower voltage cut-off [V]")
    assert d.validation_issues_empty_text() == "✓ No issues"
    assert d.validation_badge_count() == 0

    task = next(t for t in d.outstanding_tasks() if t.path == _LOWER_CUTOFF)
    assert task.kind is TaskKind.NULL_FIELD
    assert task.required is True


def test_optional_expected_null_is_grey_without_warning(app_driver, tmp_path, valid_spm_dict):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Header"]["Description"] = None
    d = app_driver
    d.open(_write(tmp_path, "optional_null.json", raw))
    d.select_object(("Header",))
    d.diagnostics_select_rail("Header")

    assert d.parameter_row_is_grey("Description")
    assert not d.parameter_row_has_warning_marker("Description")
    assert d.validation_issues_empty_text() == "✓ No issues"
    assert d.validation_badge_count() == 0

    task = next(t for t in d.outstanding_tasks() if t.path == ("Header", "Description"))
    assert task.kind is TaskKind.NULL_FIELD
    assert task.required is False


def test_custom_null_is_grey_with_warning_and_stays_red(app_driver, tmp_path, valid_spm_dict):
    """A custom parameter's extra_forbidden is name-rejection,
    value-independent -- it never absorbs, so the row stays flagged and the
    page stays red, even though the row itself is grey (empty, at a glance)."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Header"]["NotARealField"] = None
    d = app_driver
    d.open(_write(tmp_path, "custom_null.json", raw))
    d.select_object(("Header",))

    assert d.parameter_row_is_grey("NotARealField")
    assert d.parameter_row_has_warning_marker("NotARealField")
    assert d.validation_issue_count() == 1
    assert "NotARealField" in d.validation_issue_texts()[0]
    assert d.validation_badge_count() == 1
    assert d.validation_badge_severity() == "error"
    assert not any(t.path == ("Header", "NotARealField") for t in d.outstanding_tasks())


def test_filled_bad_value_stays_normal_with_warning(app_driver, tmp_path, valid_spm_dict):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Upper voltage cut-off [V]"] = "oops"
    d = app_driver
    d.open(_write(tmp_path, "filled_bad.json", raw))
    d.select_object(_CELL)

    assert not d.parameter_row_is_grey("Upper voltage cut-off [V]")
    assert d.parameter_row_has_warning_marker("Upper voltage cut-off [V]")
    assert d.validation_badge_count() >= 1


def test_filled_valid_value_stays_normal_without_warning(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)
    d.select_object(_CELL)

    assert not d.parameter_row_is_grey("Electrode area [m2]")
    assert not d.parameter_row_has_warning_marker("Electrode area [m2]")


# ---------------------------------------------------------------------------
# Absorbed diagnostics surface as Outstanding secondary text.
# ---------------------------------------------------------------------------


def test_outstanding_row_shows_the_absorbed_validator_message(app_driver, tmp_path, valid_spm_dict):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = None
    d = app_driver
    d.open(_write(tmp_path, "absorbed_message.json", raw))

    task = next(t for t in d.outstanding_tasks() if t.path == _LOWER_CUTOFF)
    text = d.outstanding_task_row_text(task)

    # The float_type+int_type pair merges to one displayed message.
    assert "Input should be a valid number" in text
    assert "Input should be a valid integer" not in text


def test_removing_state_from_a_valid_document_leaves_it_complete(app_driver, tmp_path, valid_spm_dict):
    """bpx 1.1.1 made ``State`` schema-optional and deleted the root
    validator that used to demand it ("'State' section must be provided
    unless using a 'Partial' parameterisation") -- removing it from an
    otherwise-valid document no longer produces an Outstanding row or any
    validator diagnostic at all."""
    raw = json.loads(json.dumps(valid_spm_dict))
    del raw["State"]
    d = app_driver
    d.open(_write(tmp_path, "no_state.json", raw))

    assert d.outstanding_tasks() == []
    assert d.validation_issue_count() == 0


# ---------------------------------------------------------------------------
# The float_type+int_type union pair displays as one row.
# ---------------------------------------------------------------------------


def _partial_null_capacity_path(tmp_path):
    from core import document_factory

    raw = document_factory.create("Partial", title="probe")
    raw["Parameterisation"]["Cell"] = {"Nominal cell capacity [A.h]": None}
    return _write(tmp_path, "partial_null.json", raw)


def test_union_pair_merges_in_issues_tab(app_driver, tmp_path):
    d = app_driver
    d.open(_partial_null_capacity_path(tmp_path))
    d.go_to(_CELL + ("Nominal cell capacity [A.h]",))
    d.click_issues_tab()

    assert d.issues_tab_count() == 1
    assert d.issues_tab_texts() == ["[ERROR] Input should be a valid number"]


def _partial_bad_capacity_path(tmp_path):
    """A wrong-typed (not null) FloatInt value: a committed null now absorbs
    into a NULL_FIELD task even under Partial, so a *page-visible* union pair
    needs a value that is wrong rather than empty -- a list raises the same
    ``float_type``/``int_type`` pair but stays a plain, uncalmed Issue."""
    from core import document_factory

    raw = document_factory.create("Partial", title="probe")
    raw["Parameterisation"]["Cell"] = {"Nominal cell capacity [A.h]": []}
    return _write(tmp_path, "partial_bad_capacity.json", raw)


def test_union_pair_merges_on_the_page_and_in_the_badge(app_driver, tmp_path):
    d = app_driver
    d.open(_partial_bad_capacity_path(tmp_path))

    # 4 missing Cell fields + 1 merged capacity row (not 2) = 5.
    assert d.validation_issue_count() == 5
    assert sum("capacity" in text.lower() for text in d.validation_issue_texts()) == 1
    assert d.validation_badge_count() == 5


def test_union_pair_does_not_merge_across_different_locations(app_driver, tmp_path):
    """A float_type at one parameter's location and an int_type at a
    DIFFERENT parameter's location must NOT merge -- only an exact pair at
    the SAME location does. Two distinct wrong-typed FloatInt parameters
    must render as two separate rows, not one (wrong-typed, not null --
    see ``_partial_bad_capacity_path``)."""
    from core import document_factory

    raw = document_factory.create("Partial", title="probe")
    raw["Parameterisation"]["Cell"] = {
        "Nominal cell capacity [A.h]": [],
        "Electrode area [m2]": [],
    }
    d = app_driver
    d.open(_write(tmp_path, "two_distinct_bad_values.json", raw))

    matching = [t for t in d.validation_issue_texts() if "should be a valid number" in t]
    assert len(matching) == 2


# ---------------------------------------------------------------------------
# The secondary Issues-tab BADGE must always equal its own LIST count -- two
# Inspector call-sites (live-preview, Escape-revert) used to push the
# unmerged diagnostic length into the badge while the list stayed merged.
# ---------------------------------------------------------------------------


def test_issues_tab_badge_matches_list_after_escape_revert(app_driver, tmp_path):
    """Select a committed-null FloatInt parameter: the tab lists 1 merged row
    and the badge reads 1. Edit then press Escape (``Inspector._on_reset``)
    -- the list stays at its pre-edit render (1 row, ``_on_reset`` does not
    re-run ``show_parameter``), so the badge must stay 1 too, not
    ``len(parameter.issues)`` (2, the unmerged float_type+int_type pair)."""
    d = app_driver
    d.open(_partial_null_capacity_path(tmp_path))
    d.go_to(_CELL + ("Nominal cell capacity [A.h]",))
    d.click_issues_tab()

    assert d.issues_tab_count() == 1
    assert d.issues_tab_badge_count() == 1

    d.edit_field(5.0)
    d.escape()

    assert d.issues_tab_count() == 1
    assert d.issues_tab_badge_count() == 1


def test_issues_tab_badge_matches_list_during_live_preview(app_driver, valid_spm_path):
    """``Inspector._validate_draft`` (live typing, before commit) is the
    other call-site: previewing a candidate ``None`` value on a valid
    FloatInt field raises the same float_type+int_type pair, and the badge
    must show the merged count (1), not the raw diagnostic count (2)."""
    d = app_driver
    d.open(valid_spm_path)
    d.go_to(_LOWER_CUTOFF)
    d.click_issues_tab()
    assert d.issues_tab_badge_count() == 0  # baseline: a valid committed field

    d.edit_field("")  # draft candidate becomes None -- previews the pair
    d.wait_for_live_validation()

    assert d.issues_tab_badge_count() == 1


# ---------------------------------------------------------------------------
# Value-removed flow, end to end: fill -> commit -> null -> commit.
# ---------------------------------------------------------------------------


def test_value_removed_flow_turns_the_row_grey_and_calms_the_page(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)
    d.select_object(_CELL)
    d.diagnostics_select_rail("Cell")
    assert not d.parameter_row_is_grey("Lower voltage cut-off [V]")
    assert d.validation_issues_empty_text() == "✓ No issues"
    assert not any(t.path == _LOWER_CUTOFF for t in d.outstanding_tasks())

    d.go_to(_LOWER_CUTOFF)
    d.edit_field("").commit()  # empty text commits None (core.values.parse_value)

    d.select_object(_CELL)
    assert d.parameter_row_is_grey("Lower voltage cut-off [V]")
    assert not d.parameter_row_has_warning_marker("Lower voltage cut-off [V]")
    assert d.validation_issues_empty_text() == "✓ No issues"  # still calm -- absorbed
    task = next(t for t in d.outstanding_tasks() if t.path == _LOWER_CUTOFF)
    assert task.kind is TaskKind.NULL_FIELD
    assert task.required is True
