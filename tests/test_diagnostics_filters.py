"""Diagnostics page filters.

Filters are VIEW-ONLY: strip counts, the app badge and the reconciliation
test always read the same unfiltered ``PageBuckets`` this module always
has -- filtering only decides which rows ``_StreamView``/``_add_section``
actually add to the list. Every test here either proves a row disappears/
reappears from the stream while the TRUTH layer (buckets/counts) stays
untouched, or proves the pure filter predicates (``_issue_visible``/
``_task_visible``) directly.

Amended D10 (2026-08-05): there is no "N hidden by filters" line any more.
A section whose content is entirely filtered out renders nowhere at all --
not in the stream, not on the clear line either (clear is computed
unfiltered). The reconciliation test at the bottom of this file restates
that invariant directly from bucket data + chip state, per PLAN-diagnostics-
stream.md section 6.

The text-filter field was removed (per-section buckets are small and the
toolbar search already finds anything by name); the three count chips are
the whole filter surface.
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
    """Two distinct error rows in the Cell bucket."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "banana"
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = "low"
    return _write(tmp_path, "two_cell_errors.json", raw)


# ---------------------------------------------------------------------------
# Pure predicates (_FilterState / _issue_visible / _task_visible), no Qt
# widgets -- the "small pure filter helper" the view builders consume.
# ---------------------------------------------------------------------------


def test_issue_visible_respects_its_own_severity_chip_only():
    from core.validation import PydanticErrorDiagnostic, Severity
    from ui_qt.diagnostics_panel import _FilterState, _issue_visible

    error = PydanticErrorDiagnostic(raw_error={"msg": "bad", "type": "float_type"}, severity=Severity.ERROR)
    warning = PydanticErrorDiagnostic(raw_error={"msg": "meh", "type": "x"}, severity=Severity.WARNING)

    assert _issue_visible(error, _FilterState()) is True
    assert _issue_visible(error, _FilterState(error_on=False)) is False
    assert _issue_visible(warning, _FilterState(warning_on=False)) is False
    assert _issue_visible(warning, _FilterState(error_on=False)) is True


def test_task_visible_respects_the_outstanding_chip():
    from core.completion import CompletionTask, TaskKind
    from ui_qt.diagnostics_panel import _FilterState, _task_visible

    task = CompletionTask(
        kind=TaskKind.MISSING_FIELD,
        path=("Parameterisation", "Cell", "Electrode area [m2]"),
        alias="Electrode area [m2]",
        required=True,
    )

    assert _task_visible(task, _FilterState()) is True
    assert _task_visible(task, _FilterState(outstanding_on=False)) is False


# ---------------------------------------------------------------------------
# Chip filtering, end to end -- hides exactly the right category from the
# stream, leaving truth alone.
# ---------------------------------------------------------------------------


def test_error_chip_off_hides_error_rows_but_not_counts(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    assert len(d.diagnostics_stream_issue_texts()) == 2
    assert d.diagnostics_chip_is_on("errors") is True

    d.diagnostics_toggle_chip("errors")

    assert d.diagnostics_chip_is_on("errors") is False
    assert d.diagnostics_stream_issue_texts() == []
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
    assert len(d.diagnostics_stream_task_texts()) == 24  # 5+9+9 required + 1 optional, both "task" rows
    assert d.diagnostics_stream_subhead_texts() == ["1 optional parameter unfilled"]

    d.diagnostics_toggle_chip("outstanding")

    assert d.diagnostics_stream_task_texts() == []
    assert d.diagnostics_stream_subhead_texts() == []
    # A filtered-empty section leaves no trace at all (amended D10): Cell/
    # Negative electrode/Positive electrode are entirely task-only, so all
    # three headers disappear too, leaving only Header on the clear line --
    # which keeps "clear": the scaffold's missing required values abort
    # bpx's run at Parameterisation, a stage after Header was judged (H2).
    assert d.diagnostics_stream_section_headers() == []
    assert d.diagnostics_clear_line_text() == "1 section clear"
    bucket = d.diagnostics_bucket("Cell")
    assert bucket.outstanding_count == 6


def test_chip_toggle_never_changes_the_strip_or_the_bucket_data(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    before = d.diagnostics_strip_counts()
    buckets_before = {
        label: d.diagnostics_bucket(label)
        for label in ("Header", "Cell", "Negative electrode", "Positive electrode", "State")
    }

    d.diagnostics_toggle_chip("errors")
    d.diagnostics_toggle_chip("warnings")
    d.diagnostics_toggle_chip("outstanding")

    assert d.diagnostics_strip_counts() == before
    for label, bucket_before in buckets_before.items():
        bucket_after = d.diagnostics_bucket(label)
        assert (bucket_after.error_count, bucket_after.warning_count, bucket_after.outstanding_count) == (
            bucket_before.error_count,
            bucket_before.warning_count,
            bucket_before.outstanding_count,
        )


# ---------------------------------------------------------------------------
# D13: a chip whose unfiltered count is zero renders disabled -- it filters
# nothing, so it must not look pressable, and a click on it must be a
# structural no-op.
# ---------------------------------------------------------------------------


def test_zero_count_chip_is_disabled_and_a_click_does_nothing(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)  # errors only -- zero outstanding
    assert d.diagnostics_strip_counts()[2] == 0
    assert d.diagnostics_chip_is_enabled("outstanding") is False
    assert d.diagnostics_chip_is_enabled("errors") is True

    d.diagnostics_toggle_chip("outstanding")

    assert d.diagnostics_chip_is_on("outstanding") is True  # click did nothing


@pytest.fixture
def many_issues_path(tmp_path, valid_spm_dict):
    """Errors spread across three sections, zero outstanding work -- shared
    with the zero-count-chip and all-chips-off tests below."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "banana"
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = "low"
    raw["Parameterisation"]["Negative electrode"]["Thickness [m]"] = "thin"
    raw["Parameterisation"]["Positive electrode"]["Diffusivity [m2.s-1]"] = "fast"
    return _write(tmp_path, "many_issues.json", raw)


# ---------------------------------------------------------------------------
# All chips off: no sections render at all, but the clear line stays true
# (clean buckets never depended on the filter in the first place).
# ---------------------------------------------------------------------------


def test_all_chips_off_no_sections_render_but_the_clear_line_still_holds(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)

    d.diagnostics_toggle_chip("errors")
    d.diagnostics_toggle_chip("warnings")

    assert d.diagnostics_stream_section_headers() == []
    # Header, State -- unaffected by filters, split by what the run judged
    # (H2): the errors abort bpx at Parameterisation, after Header was
    # judged and before State ever was.
    assert d.diagnostics_clear_line_text() == "1 section clear · 1 not checked"


# ---------------------------------------------------------------------------
# Amended D10: a section entirely filtered out (every one of its rows
# suppressed) renders no trace at all -- no header, no hidden-count line
# (there is no such line any more), not on the clear line either.
# ---------------------------------------------------------------------------


def test_filtered_empty_section_renders_no_header_at_all(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    assert "Cell" in " ".join(d.diagnostics_stream_headers())

    d.diagnostics_toggle_chip("errors")
    assert "Cell" not in " ".join(d.diagnostics_stream_headers())
    assert "Cell" not in " ".join(d.diagnostics_clear_section_texts())  # not on the clear line either

    d.diagnostics_toggle_chip("errors")
    assert "Cell" in " ".join(d.diagnostics_stream_headers())


# ---------------------------------------------------------------------------
# Fold state composes independently of filters: a fold-collapsed section's
# rows stay collapsed regardless of what a chip does -- covered end to end
# by the reconciliation test at the bottom of this file.
# ---------------------------------------------------------------------------


def test_folded_section_rows_do_not_reappear_because_a_chip_was_toggled(app_driver):
    d = app_driver
    d._w._new("SPM")
    d.diagnostics_fold_section("Cell")
    task_texts_before = d.diagnostics_stream_task_texts()

    d.diagnostics_toggle_chip("outstanding")
    d.diagnostics_toggle_chip("outstanding")

    assert d.diagnostics_stream_task_texts() == task_texts_before  # still folded, not re-shown


# ---------------------------------------------------------------------------
# Persistence: like rail selection, filter state survives an ordinary
# refresh and resets only for a different document.
# ---------------------------------------------------------------------------


def test_filter_state_persists_across_a_commit_triggered_refresh(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_toggle_chip("errors")

    d._w._state.active.apply_value(("Parameterisation", "Cell", "Volume [m3]"), 1.0)
    d._w._refresh_all()

    assert d.diagnostics_chip_is_on("errors") is False


def test_filter_state_resets_on_a_new_document(app_driver, two_cell_errors_path, monkeypatch):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_toggle_chip("errors")

    from ui_qt import main_window as main_window_module

    # accept the clean-document replace confirm New now shows
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *a, **k: main_window_module.QMessageBox.Ok,
    )
    d._w._new("SPM")

    assert d.diagnostics_chip_is_on("errors") is True
    assert d.diagnostics_chip_is_on("warnings") is True
    assert d.diagnostics_chip_is_on("outstanding") is True


# ---------------------------------------------------------------------------
# Activation still works on visible rows while filters are active.
# ---------------------------------------------------------------------------


def test_activation_navigates_to_the_correct_visible_row_while_filtered(app_driver, two_cell_errors_path):
    d = app_driver
    d.open(two_cell_errors_path)
    d.diagnostics_toggle_chip("outstanding")

    visible = d._validation_rows("issue")
    assert len(visible) == 2
    lower = [row for row in visible if "Lower voltage" in row.text()]
    assert len(lower) == 1
    d.activate_validation_row(lower[0])

    assert d.inspector_title() == "Lower voltage cut-off [V]"


# ---------------------------------------------------------------------------
# With every chip off, the truth layer (buckets/badges) must still fully
# reconcile -- it never saw the filter at all.
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

    assert d._validation_rows("issue") == []
    assert d._validation_rows("task") == []
    assert d.diagnostics_strip_counts() == (errors, warnings, outstanding)
    assert d.validation_badge_count() == app_badge
    assert d.validation_badge_severity() == app_severity


# ---------------------------------------------------------------------------
# The reconciliation test (D2's safety net, restated for the stream --
# PLAN-diagnostics-stream.md section 6): every diagnostic and every task in
# PageBuckets is accounted for exactly once by rendered rows + rows
# suppressed by chip state + clear-section rows (always zero -- a clear
# bucket has nothing to suppress by definition). No hidden line renders any
# more (amended D10), so the suppressed count is computed here directly
# from the bucket data and the chip state -- never read back from a UI
# line -- and nothing must render that ``PageBuckets`` does not contain.
# ---------------------------------------------------------------------------


def _reconcile(d, filters):
    from ui_qt.diagnostics_panel import _issue_visible, _task_visible

    buckets = d._w._diagnostics._buckets
    total_issues = sum(len(b.issues) for b in buckets.buckets)
    total_tasks = sum(len(b.required_tasks) + len(b.optional_tasks) for b in buckets.buckets)
    suppressed_issues = sum(
        1 for b in buckets.buckets for diagnostic, _nav_path in b.issues if not _issue_visible(diagnostic, filters)
    )
    suppressed_tasks = sum(
        1
        for b in buckets.buckets
        for task in (*b.required_tasks, *b.optional_tasks)
        if not _task_visible(task, filters)
    )
    rendered_issues = len(d.diagnostics_stream_issue_texts())
    rendered_tasks = len(d.diagnostics_stream_task_texts())

    assert rendered_issues + suppressed_issues == total_issues
    assert rendered_tasks + suppressed_tasks == total_tasks
    # Nothing renders that PageBuckets does not contain: every rendered
    # section header names a real, non-clear bucket (the file-facts group,
    # S1, is not a bucket at all and is excluded from this check).
    bucket_labels = {b.label for b in buckets.buckets}
    for header in d.diagnostics_stream_section_headers():
        assert any(header.startswith(label) for label in bucket_labels)


def test_reconciliation_holds_with_one_chip_off(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    d.diagnostics_toggle_chip("errors")

    _reconcile(d, d._w._diagnostics._strip.filter_state())


def test_reconciliation_holds_with_every_chip_off(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    d.diagnostics_toggle_chip("errors")
    d.diagnostics_toggle_chip("warnings")
    d.diagnostics_toggle_chip("outstanding")

    assert d.diagnostics_stream_section_headers() == []  # everything suppressed
    _reconcile(d, d._w._diagnostics._strip.filter_state())


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


# ---------------------------------------------------------------------------
# Row content: what an outstanding row does not repeat, and how wide it gets
# ---------------------------------------------------------------------------


def test_a_missing_field_row_does_not_repeat_itself(app_driver):
    """Absorption seats a "missing" diagnostic under the very task that
    describes the same absent field, so printing its message under the row
    said "REQUIRED" and "Field required" on every one of thirty-five rows.
    A structural drop, not a reading of the validator's words."""
    from ui_qt.diagnostics_panel import _absorbed_messages

    app_driver._w._new("DFN")
    partition = app_driver._w._diagnostics._partition
    missing = [
        task
        for task in partition.absorbed_by_task
        if task.kind.name.startswith("MISSING")
    ]
    assert missing, "expected a fresh DFN to carry absorbed missing-field tasks"
    for task in missing:
        assert _absorbed_messages(task, partition) == ()


def test_stream_rows_stop_at_a_readable_measure(app_driver, tmp_path):
    """A validator message ran the full bleed on a wide window, and its
    right-aligned "Go to ▸" ended up a thousand pixels from its own row."""
    from PySide6.QtWidgets import QStyleOptionViewItem

    from ui_qt.diagnostics_panel import _DiagnosticsRowDelegate

    delegate = _DiagnosticsRowDelegate(None)
    option = QStyleOptionViewItem()
    option.rect.setWidth(1400)

    assert delegate._measured(option).rect.width() == delegate._MEASURE

    # A window narrower than the measure is left exactly as it is.
    option.rect.setWidth(500)
    assert delegate._measured(option).rect.width() == 500
