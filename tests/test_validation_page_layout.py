"""Diagnostics page -- rail redesign (Stage B, 2026-07-16 design pass).

Replaces the old Concept A layout (collapsible issue-section groups, two
page-level "Issues"/"Outstanding" headers sharing one QListWidget) with the
signed-off wireframe: a summary strip, a section rail, and a detail pane
that is either one selected section's Issues/Outstanding group boxes or the
whole-document "All sections" backup view. See ``ui_qt.diagnostics_panel``'s
module docstring and ``PLAN-completion-track.md`` S4b (decisions F2-F7) for
the full design. Companion fix carried over unchanged from Concept A: a bad
*string* in a FloatInt field (float_parsing + int_parsing) merges to one
displayed row (decision Q), so its badge count and its rows agree.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from ui_qt.diagnostics_panel import _MSG_NO_ISSUES, _MSG_NOTHING_OUTSTANDING

_CELL = ("Parameterisation", "Cell")


def _write(tmp_path, name: str, raw: dict):
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


@pytest.fixture
def many_issues_path(tmp_path, valid_spm_dict):
    """A document with errors spread across three sections + one absorbed
    null, so the rail badges and All-sections grouping have something to
    show."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "banana"
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = "low"
    raw["Parameterisation"]["Negative electrode"]["Thickness [m]"] = "thin"
    raw["Parameterisation"]["Positive electrode"]["Diffusivity [m2.s-1]"] = "fast"
    return _write(tmp_path, "many_issues.json", raw)


# --- summary strip ---------------------------------------------------------


def test_strip_counts_wording(qtbot):
    """The strip's pure count -> chip-text mapping, singular/plural handled
    per side -- the direct descendant of the old page-header count-suffix
    helpers, now rendered as three always-visible chips instead of a
    conditional header suffix."""
    from ui_qt.diagnostics_panel import _SummaryStrip

    strip = _SummaryStrip()
    qtbot.addWidget(strip)

    strip.set_counts(0, 0, 0)
    assert "0 error" in strip._errors.text() and "0 warning" in strip._warnings.text()
    assert "0 outstanding" in strip._outstanding.text()

    strip.set_counts(1, 0, 0)
    assert "1 error" in strip._errors.text()
    assert "1 errors" not in strip._errors.text()

    strip.set_counts(4, 1, 12)
    assert "4 errors" in strip._errors.text()
    assert "1 warning" in strip._warnings.text()
    assert "1 warnings" not in strip._warnings.text()
    assert "12 outstanding" in strip._outstanding.text()


def test_strip_totals_match_the_app_rail_badge(app_driver, many_issues_path):
    """F3/G: the strip's totals and the app-rail badge derive from the same
    ``PartitionedIssues`` in ``main_window._refresh_all`` -- they can never
    disagree."""
    d = app_driver
    d.open(many_issues_path)
    errors, warnings, _outstanding = d.diagnostics_strip_counts()
    assert errors + warnings == d.validation_badge_count()


# --- rail --------------------------------------------------------------


def test_rail_lists_all_sections_first_then_one_entry_per_bucket(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    labels = d.diagnostics_rail_labels()
    assert labels[0] == "All sections"
    # SPM's schema sections, in document order, present or not (F3: every
    # SectionBucket gets a rail entry, clean or not).
    assert labels[1:] == ["Header", "Cell", "Negative electrode", "Positive electrode", "State"]


def test_clean_bucket_shows_no_badge(app_driver, many_issues_path):
    """F4: a clean bucket carries no badge at all -- quiet rail, not a
    green/zero one."""
    d = app_driver
    d.open(many_issues_path)
    assert d.diagnostics_rail_has_badge("Cell") is True  # 2 merged errors
    assert d.diagnostics_rail_has_badge("State") is False  # untouched, clean


def test_rail_badge_counts_match_the_bucket(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    cell = d.diagnostics_bucket("Cell")
    assert cell.error_count == 2  # two merged union-pair rows (decision Q)
    assert cell.warning_count == 0
    electrode = d.diagnostics_bucket("Negative electrode")
    assert electrode.error_count == 1


def test_absent_section_renders_italic_with_a_grey_badge(app_driver, tmp_path):
    from core import document_factory

    raw = document_factory.create("SPMe", title="probe")
    del raw["Parameterisation"]["Electrolyte"]
    d = app_driver
    d.open(_write(tmp_path, "absent_electrolyte.json", raw))

    assert d.diagnostics_rail_absent("Electrolyte") is True
    assert d.diagnostics_rail_has_badge("Electrolyte") is True
    bucket = d.diagnostics_bucket("Electrolyte")
    assert bucket.outstanding_count == 1
    assert bucket.error_count == 0


def test_document_bucket_appears_only_when_occupied(app_driver, valid_spm_path, fixtures_dir):
    d = app_driver
    d.open(valid_spm_path)
    assert "Document" not in d.diagnostics_rail_labels()

    d.open(fixtures_dir / "nmc_pouch_cell_BPX.json")
    labels = d.diagnostics_rail_labels()
    assert "Document" in labels
    # F2: Document sits first among the section entries, right after "All
    # sections" (the separator between them is not itself a labelled entry).
    assert labels[1] == "Document"


def test_document_bucket_issue_with_no_attachment_point_is_a_no_op(app_driver, fixtures_dir):
    """A Document-bucket row's nav_path is whatever the attachment pass
    resolved -- for the nmc fixture's own diagnostic (a bare Python warning,
    no ``.loc`` at all) that is an empty tuple, and ``NavigationService.
    navigate`` already no-ops on an empty path, so activation must not
    raise or change the current selection."""
    d = app_driver
    d.open(fixtures_dir / "nmc_pouch_cell_BPX.json")
    document_bucket = d.diagnostics_bucket("Document")
    assert document_bucket is not None
    diagnostic, nav_path = document_bucket.issues[0]
    assert nav_path == ()

    before = d.tree_selection_label()
    d.activate_validation_issue(nav_path)  # must not raise

    assert d.tree_selection_label() == before


def test_default_selection_is_all_sections(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)
    assert d.diagnostics_selected_rail_label() == "All sections"
    assert d.diagnostics_pane_mode() == "all"


def test_rail_selection_switches_the_pane_and_never_mutates_the_document(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    assert d.undo_enabled() is False

    d.diagnostics_select_rail("Cell")

    assert d.diagnostics_pane_mode() == "section"
    assert d.diagnostics_selected_rail_label() == "Cell"
    assert d.undo_enabled() is False  # selection alone never mutates


def test_rail_arrow_keys_move_selection(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    d.diagnostics_select_rail("All sections")

    d.diagnostics_rail_press_down()  # skips the non-selectable separator

    assert d.diagnostics_selected_rail_label() not in (None, "All sections")
    assert d.diagnostics_pane_mode() == "section"


def test_rail_selection_persists_across_a_commit_triggered_refresh(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    d.diagnostics_select_rail("Cell")

    d._w._state.active.apply_value(("Parameterisation", "Cell", "Volume [m3]"), 1.0)
    d._w._refresh_all()

    assert d.diagnostics_selected_rail_label() == "Cell"


def test_rail_selection_resets_to_all_sections_on_a_new_document(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    d.diagnostics_select_rail("Cell")
    assert d.diagnostics_selected_rail_label() == "Cell"

    d._w._new("SPM")

    assert d.diagnostics_selected_rail_label() == "All sections"


# --- section detail pane ----------------------------------------------------


def test_selecting_a_section_shows_only_its_own_rows(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)

    d.diagnostics_select_rail("Cell")
    assert len(d.diagnostics_section_issue_texts()) == 2
    assert all("Cell" not in text.split(":")[0] for text in d.diagnostics_section_issue_texts())

    d.diagnostics_select_rail("Negative electrode")
    assert len(d.diagnostics_section_issue_texts()) == 1


def test_header_owned_issue_shows_in_the_header_section(app_driver, tmp_path, valid_spm_dict):
    """``Parameterisation`` is a structural wrapper stripped for display, but
    ``Header`` is itself a meaningful section and must not be: a bad
    ``Header.Model`` lands in the "Header" bucket, not somewhere else."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Header"]["Model"] = "banana"
    d = app_driver
    d.open(_write(tmp_path, "bad_header.json", raw))

    assert d.diagnostics_bucket("Header").error_count == 1
    d.diagnostics_select_rail("Header")
    assert len(d.diagnostics_section_issue_texts()) == 1


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
    # is muted, the message present, and no bracketed [ERROR] tag survives
    # (F5: a delegate-painted icon carries severity now).
    assert "<br>" in row
    assert "Lower voltage cut-off" in row
    assert "[V]" in row
    assert "Input should be a valid number" in row
    assert "[ERROR]" not in row and "[WARN]" not in row


def test_issue_rows_carry_the_severity_role_for_the_delegate_icon(app_driver, many_issues_path):
    from ui_qt import parameter_row

    d = app_driver
    d.open(many_issues_path)
    d.diagnostics_select_rail("Cell")
    lst = d._w._diagnostics._section_view._issues_box.list
    severities = {lst.item(i).data(parameter_row.SEVERITY_ROLE) for i in range(lst.count())}
    assert severities == {"error"}


def test_issues_box_badge_shows_a_warning_only_bucket(app_driver, fixtures_dir):
    """Regression: the Issues box header used to pass only ``bucket.
    error_count`` to its badge, so a warnings-only bucket (no errors) drew
    an invisible "0" badge even though its one warning row rendered fine.
    The header must match the rail's own badge rule (F4/F5): an amber badge
    when warnings are nonzero, no red badge when errors are zero."""
    d = app_driver
    d.open(fixtures_dir / "warning_legacy_bpx_float.json")
    bucket = d.diagnostics_bucket("Document")
    assert bucket.error_count == 0
    assert bucket.warning_count == 1

    d.diagnostics_select_rail("Document")

    assert d.diagnostics_section_issues_badge_texts() == ["1"]


def test_box_headers_carry_the_ratio_copy(app_driver):
    d = app_driver
    d._w._new("SPM")
    d.diagnostics_select_rail("Cell")

    assert "Cell" in d.diagnostics_section_header_text()
    assert d.diagnostics_section_outstanding_title() == "Outstanding · 5 of 5 remaining"
    assert d.diagnostics_section_issues_badge_texts() == []  # no badge at all on a clean bucket


def test_optional_subhead_only_when_optional_tasks_exist(app_driver, tmp_path):
    from core import document_factory

    raw = document_factory.create("SPM", title="probe")
    d = app_driver
    d.open(_write(tmp_path, "no_optional.json", raw))
    d.diagnostics_select_rail("Cell")
    assert d.diagnostics_section_optional_subhead_texts() == []

    raw["Parameterisation"]["Cell"]["Volume [m3]"] = None
    d.open(_write(tmp_path, "with_optional.json", raw))
    d.diagnostics_select_rail("Cell")
    subheads = d.diagnostics_section_optional_subhead_texts()
    assert subheads == ["OPTIONAL - 1 UNFILLED"]


def test_section_pane_empty_states_use_pinned_words(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)
    d.diagnostics_select_rail("Header")

    assert d.diagnostics_section_issues_empty_text() == _MSG_NO_ISSUES
    assert d.diagnostics_section_outstanding_empty_text() == _MSG_NOTHING_OUTSTANDING


# --- All sections (F3 backup view) ------------------------------------------


def test_all_sections_renders_every_bucket_exactly_once(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    fold_labels = [label for label, _collapsed in d.all_sections_fold_headers()]
    assert fold_labels == d.diagnostics_rail_labels()[1:]  # every bucket, same order, none twice


def test_all_sections_row_identity_matches_the_buckets(app_driver, many_issues_path):
    """Spot-check the backup guarantee at UI level (F3): every issue row
    shown in All-sections belongs to the bucket the rail agrees it does."""
    d = app_driver
    d.open(many_issues_path)
    cell_bucket = d.diagnostics_bucket("Cell")
    assert cell_bucket.error_count == 2
    assert len(d.validation_issue_texts()) == sum(
        d.diagnostics_bucket(label).error_count + d.diagnostics_bucket(label).warning_count
        for label in d.diagnostics_rail_labels()[1:]
        if d.diagnostics_bucket(label) is not None
    )


def test_only_issue_and_task_rows_are_interactive():
    """Headers, sub-heads and messages paint flat -- the delegate strips
    hover/selection for every kind outside this set. A highlight promises
    interaction; activating those rows is a structural no-op."""
    from ui_qt.diagnostics_panel import _DiagnosticsRowDelegate

    assert _DiagnosticsRowDelegate._INTERACTIVE_KINDS == {"issue", "task"}


def test_fold_header_paints_as_a_fixed_height_band(app_driver, valid_spm_path):
    """Fold headers get a fixed-height band treatment (the delegate
    overrides sizeHint for them), the direct descendant of Concept A's
    page-header divider."""
    from PySide6.QtWidgets import QStyleOptionViewItem

    from ui_qt.diagnostics_panel import _DiagnosticsRowDelegate

    d = app_driver
    d.open(valid_spm_path)
    lst = d._w._diagnostics._all_view._list
    header = d._validation_rows("fold_header")[0]
    index = lst.indexFromItem(header)
    option = QStyleOptionViewItem()
    option.font = lst.font()
    assert lst.itemDelegate().sizeHint(option, index).height() == _DiagnosticsRowDelegate._FOLD_HEADER_HEIGHT


# --- fold ------------------------------------------------------------------


def test_folding_a_bucket_hides_both_its_issue_and_task_rows(app_driver, tmp_path, valid_spm_dict):
    """Fold is per-bucket now (issues + outstanding together), not per-
    Issues-section -- the direct architectural change from Concept A. Uses
    a Cell bucket that genuinely carries BOTH an issue (a bad value) and a
    task (a deleted required field), so folding is proved to hide each
    half of its own claim, not just the one a fresh skeleton happens to have."""
    raw = json.loads(json.dumps(valid_spm_dict))
    del raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = "low"
    d = app_driver
    d.open(_write(tmp_path, "cell_issue_and_task.json", raw))

    cell_bucket = d.diagnostics_bucket("Cell")
    assert len(cell_bucket.issues) == 1
    assert len(cell_bucket.required_tasks) == 1
    issues_before = len(d.validation_issue_texts())
    tasks_before = len(d.validation_task_texts())

    d.toggle_all_sections_fold("Cell")

    assert ("Cell", True) in d.all_sections_fold_headers()
    assert len(d.validation_issue_texts()) == issues_before - 1
    assert len(d.validation_task_texts()) == tasks_before - 1

    d.toggle_all_sections_fold("Cell")
    assert ("Cell", False) in d.all_sections_fold_headers()
    assert len(d.validation_issue_texts()) == issues_before
    assert len(d.validation_task_texts()) == tasks_before


def test_fold_survives_a_refresh(app_driver):
    d = app_driver
    d._w._new("SPM")
    d.toggle_all_sections_fold("Cell")
    assert ("Cell", True) in d.all_sections_fold_headers()

    d._w._state.active.apply_value(("Header", "Title"), "still folded")
    d._w._refresh_all()

    assert ("Cell", True) in d.all_sections_fold_headers()


def test_fold_does_not_leak_into_a_new_document(app_driver):
    d = app_driver
    d._w._new("SPM")
    d.toggle_all_sections_fold("Cell")
    assert ("Cell", True) in d.all_sections_fold_headers()

    d._w._state.active.dirty = False  # avoid the offscreen-blocking discard dialog
    d._w._new("SPM")

    assert ("Cell", False) in d.all_sections_fold_headers()


def test_fold_does_not_leak_into_the_next_opened_document(
    app_driver, many_issues_path, tmp_path, valid_spm_dict
):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Electrode area [m2]"] = "wide"
    other = _write(tmp_path, "other_issues.json", raw)

    d = app_driver
    d.open(many_issues_path)
    d.toggle_all_sections_fold("Cell")
    assert ("Cell", True) in d.all_sections_fold_headers()

    d.open(other)
    assert ("Cell", False) in d.all_sections_fold_headers()


# --- clean document ----------------------------------------------------------


def test_clean_document_has_no_rail_badges(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)
    assert d.diagnostics_strip_counts() == (0, 0, 0)
    for label in d.diagnostics_rail_labels():
        assert d.diagnostics_rail_has_badge(label) is False


# --- _ratio_words (pure function, all branches) -----------------------------


def _bucket(
    path=("Parameterisation", "Cell"),
    label="Cell",
    absent=False,
    required_tasks=(),
    optional_tasks=(),
    required_total=0,
):
    from core.page_buckets import SectionBucket

    return SectionBucket(
        path=path,
        label=label,
        absent=absent,
        issues=(),
        required_tasks=required_tasks,
        optional_tasks=optional_tasks,
        required_total=required_total,
        error_count=0,
        warning_count=0,
    )


def _task(kind, path):
    from core.completion import CompletionTask

    return CompletionTask(kind=kind, path=path, alias=path[-1], required=True)


def test_ratio_words_document_bucket():
    from core.completion import TaskKind
    from core.page_buckets import DOCUMENT_BUCKET_PATH
    from ui_qt.diagnostics_panel import _ratio_words

    bucket = _bucket(
        path=DOCUMENT_BUCKET_PATH,
        label="Document",
        required_tasks=(_task(TaskKind.MISSING_SECTION, ("Parameterisation",)),),
        required_total=0,
    )
    assert _ratio_words(bucket) == "1 remaining"


def test_ratio_words_absent_section():
    from ui_qt.diagnostics_panel import _ratio_words

    bucket = _bucket(absent=True, required_total=None)
    assert _ratio_words(bucket) == "section absent"


def test_ratio_words_plain_ratio():
    from core.completion import TaskKind
    from ui_qt.diagnostics_panel import _ratio_words

    bucket = _bucket(
        required_tasks=(_task(TaskKind.MISSING_FIELD, ("Parameterisation", "Cell", "X")),),
        required_total=5,
    )
    assert _ratio_words(bucket) == "1 of 5 remaining"


def test_ratio_words_absent_children_only():
    """The State-like shape (Stage A groups a present section's absent
    children into its own bucket): no leaf fields required, one or more
    MISSING_SECTION children -- reports "N sections absent", never a
    misleading "0 of 0 remaining" (the case the confirmed-live bug came
    from)."""
    from core.completion import TaskKind
    from ui_qt.diagnostics_panel import _ratio_words

    one_child = _bucket(
        path=("State",),
        label="State",
        required_tasks=(_task(TaskKind.MISSING_SECTION, ("State", "Thermal environment")),),
        required_total=0,
    )
    assert _ratio_words(one_child) == "1 section absent"

    two_children = _bucket(
        path=("State",),
        label="State",
        required_tasks=(
            _task(TaskKind.MISSING_SECTION, ("State", "Initial conditions")),
            _task(TaskKind.MISSING_SECTION, ("State", "Thermal environment")),
        ),
        required_total=0,
    )
    assert _ratio_words(two_children) == "2 sections absent"



# --- windowed-review fix round (2026-07-16, second pass) -------------------
#
# Four divergences from the signed-off wireframe found by driving the real
# (non-offscreen) app: content-hugging group boxes, right-aligned task-row
# action text, bordered summary-strip chips, and rail/fold-header badge
# paint order. A fifth item (fold chevron glyph) was investigated and found
# already correct -- pinned here anyway as a regression guard.


def test_group_boxes_hug_their_content_instead_of_stretching(app_driver):
    """The confirmed layout bug: both boxes used to split the pane's full
    height ~50/50 regardless of content, so a one-row box was ~300px of
    mostly empty card. The box's list must report a content-driven
    sizeHint (via _ContentSizedList) that scales with its own row count,
    not a fixed/stretched share of the pane."""
    d = app_driver
    d._w._new("SPM")

    d.diagnostics_select_rail("Header")
    header_outstanding_height = d._w._diagnostics._section_view._outstanding_box.list.sizeHint().height()

    d.diagnostics_select_rail("Negative electrode")
    electrode_outstanding_height = d._w._diagnostics._section_view._outstanding_box.list.sizeHint().height()

    # Header's Outstanding box holds one pinned message row; Negative
    # electrode's holds 9 required task rows -- a real content-hugging box
    # must differ by far more than any fixed chrome/padding could explain.
    assert electrode_outstanding_height > header_outstanding_height * 3
    # And the small box must actually BE small -- not merely smaller than
    # its sibling while still stretched to fill most of the pane.
    assert header_outstanding_height < 60


def test_task_row_action_text_is_a_separate_right_aligned_role(app_driver):
    """S4b F5: REQUIRED sits inline after the name; the action text is
    painted separately, right-aligned, in accent colour -- not folded into
    the same parenthetical the way it used to render
    ("Name (REQUIRED . Go to >)")."""
    from ui_qt import diagnostics_panel as dp
    from ui_qt import parameter_row

    d = app_driver
    d._w._new("SPM")
    d.diagnostics_select_rail("Cell")
    lst = d._w._diagnostics._section_view._outstanding_box.list
    task_item = next(lst.item(i) for i in range(lst.count()) if lst.item(i).data(dp._KIND_ROLE) == "task")

    assert task_item.data(parameter_row.ACTION_ROLE) == "Go to ›"
    html = task_item.data(parameter_row.HTML_ROLE)
    assert "REQUIRED" in html
    assert "Go to" not in html  # action text lives in ACTION_ROLE, not the HTML fragment
    assert "· Go to ›" not in task_item.text()  # plain text no longer parenthesises it with REQUIRED


def test_summary_strip_chips_are_bordered_boxes(app_driver, valid_spm_path):
    """The wireframe's "boxes/shading to make regions distinguishable" --
    plain coloured text was a Stage-B divergence; each chip must be its own
    QSS-styled card."""
    d = app_driver
    d.open(valid_spm_path)
    strip = d._w._diagnostics._strip
    for chip in (strip._errors, strip._warnings, strip._outstanding):
        assert chip.objectName() == "DiagnosticsChip"


def test_paint_badges_paints_in_reversed_order_so_first_spec_reads_leftmost(monkeypatch):
    """Cosmetic fix: specs are built error-first (most severe first), but
    _paint_one_badge anchors each badge to the RIGHT edge and walks
    leftward, so painting in list order would put the LAST (least severe)
    spec leftmost. _paint_badges must walk specs in reverse so the first
    (most severe) spec is painted last -- landing leftmost, reading
    left-to-right in priority order -- consistently for both the rail and
    the All-sections fold headers (both call this one function)."""
    from PySide6.QtCore import QRect

    from ui_qt import diagnostics_panel as dp

    calls = []

    def fake_paint_one_badge(painter, right_x, y_mid, text, bg, fg):
        calls.append(text)
        return right_x - 20

    monkeypatch.setattr(dp, "_paint_one_badge", fake_paint_one_badge)
    specs = [("1", "r-bg", "r-fg"), ("2", "a-bg", "a-fg"), ("3", "g-bg", "g-fg")]

    dp._paint_badges(None, QRect(0, 0, 100, 20), specs)

    assert calls == ["3", "2", "1"]  # painted right-to-left -> "1" ends up leftmost on screen


def test_fold_header_glyph_flips_with_collapsed_state(app_driver):
    """Verified against a real windowed screenshot per the review: the
    chevron glyph does flip correctly with fold state (this pins the
    plain-text half of that against regression -- the delegate's own
    painted chevron is computed from the same collapsed flag, see
    _DiagnosticsRowDelegate._paint_fold_header)."""
    from ui_qt import diagnostics_panel as dp

    d = app_driver
    d._w._new("SPM")
    header = next(item for item in d._validation_rows("fold_header") if item.data(dp._FOLD_BUCKET_ROLE).label == "Cell")
    assert header.text().startswith("▾")

    d.toggle_all_sections_fold("Cell")
    header = next(item for item in d._validation_rows("fold_header") if item.data(dp._FOLD_BUCKET_ROLE).label == "Cell")
    assert header.text().startswith("▸")


# --- polish round (2026-07-17): flat dots, tooltips, crisper boxes ---------


def test_task_row_tooltip_is_task_kind_derived(app_driver):
    """Drift-safe: the tooltip is looked up from the task's own ``kind``
    enum via ``style.task_kind_tooltip`` -- never from its alias/path text."""
    from core.completion import TaskKind
    from ui_qt import diagnostics_panel as dp
    from ui_qt import style

    d = app_driver
    d._w._new("SPM")
    d.diagnostics_select_rail("Cell")
    lst = d._w._diagnostics._section_view._outstanding_box.list
    task_item = next(lst.item(i) for i in range(lst.count()) if lst.item(i).data(dp._KIND_ROLE) == "task")
    task = task_item.data(dp._TASK_ROLE)

    assert task.kind is TaskKind.MISSING_FIELD  # a fresh Cell skeleton's tasks are all missing fields
    assert task_item.toolTip() == style.task_kind_tooltip(task.kind)


def test_strip_chip_tooltips_reflect_counts(app_driver, many_issues_path):
    from ui_qt import style

    d = app_driver
    d.open(many_issues_path)
    strip = d._w._diagnostics._strip
    errors, warnings, outstanding = d.diagnostics_strip_counts()

    assert strip._errors.toolTip() == style.error_count_tooltip(errors)
    assert strip._warnings.toolTip() == style.warning_count_tooltip(warnings)
    assert strip._outstanding.toolTip() == style.outstanding_count_tooltip(outstanding)


def test_rail_entry_tooltip_reflects_bucket_counts(app_driver, many_issues_path):
    from ui_qt import style

    d = app_driver
    d.open(many_issues_path)
    cell = d.diagnostics_bucket("Cell")

    item = d._diagnostics_rail_item("Cell")

    assert item.toolTip() == style.counts_tooltip(cell.error_count, cell.warning_count, cell.outstanding_count)
    assert item.toolTip() != ""  # premise: Cell actually has something to report


def test_rail_all_sections_tooltip_reflects_document_totals(app_driver, many_issues_path):
    from ui_qt import style

    d = app_driver
    d.open(many_issues_path)
    errors, warnings, outstanding = d.diagnostics_strip_counts()

    item = d._diagnostics_rail_item("All sections")

    assert item.toolTip() == style.counts_tooltip(errors, warnings, outstanding)


def test_clean_bucket_rail_tooltip_is_empty(app_driver, many_issues_path):
    """F4's quiet philosophy extends to tooltips: a clean bucket (State,
    untouched in the many_issues fixture) has nothing to report, so its
    tooltip is empty -- no "0 errors" noise on hover."""
    d = app_driver
    d.open(many_issues_path)
    item = d._diagnostics_rail_item("State")
    assert item.toolTip() == ""


def test_severity_dots_carry_no_inner_glyph_text_in_the_delegate(app_driver, many_issues_path):
    """The confirmed real-window feedback: the delegate paints a flat dot,
    not an icon-in-circle. Structural proof (paint is a no-op to assert
    against directly): the delegate's severity-icon painter no longer draws
    any glyph text -- inspect its source rather than pixels, since colour-
    only circle painting is already covered by test_activity_bar.py-style
    pixel probes elsewhere in this suite for the equivalent badge pattern."""
    from ui_qt.parameter_row import ParameterRowDelegate

    import inspect

    source = inspect.getsource(ParameterRowDelegate._paint_severity_icon)
    assert "drawText" not in source
    assert "✕" not in source and '"!"' not in source


def test_task_glyph_is_muted_grey_not_bold(app_driver):
    """Harmonisation ask: a task row's ring/half-filled mark must render in
    the same grey (#57606a) family as the issue dots -- the shared dot
    family (unified symbol system, Concept A), rendered muted rather than
    swept into the bold name span the way a text glyph used to be."""
    from ui_qt import diagnostics_panel as dp
    from ui_qt import icons, parameter_row, style

    d = app_driver
    d._w._new("SPM")
    d.diagnostics_select_rail("Cell")
    lst = d._w._diagnostics._section_view._outstanding_box.list
    task_item = next(lst.item(i) for i in range(lst.count()) if lst.item(i).data(dp._KIND_ROLE) == "task")
    html = task_item.data(parameter_row.HTML_ROLE)
    task = task_item.data(dp._TASK_ROLE)

    expected_glyph = icons.html_img(dp._task_glyph_svg(task), color=style.MUTED, size=parameter_row.MARK_BOX)
    assert html.startswith(expected_glyph)
