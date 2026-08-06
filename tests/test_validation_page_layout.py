"""Diagnostics page: summary strip + one scrolling stream.

See ``ui_qt.diagnostics_panel``'s module docstring and ``PLAN-diagnostics-
stream.md`` for the full design. A bad *string* in a FloatInt field
(float_parsing + int_parsing) merges to one displayed row, so its badge
count and its rows agree.
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
    assert "0 incomplete" in strip._outstanding.text()

    strip.set_counts(1, 0, 0)
    assert "1 error" in strip._errors.text()
    assert "1 errors" not in strip._errors.text()

    strip.set_counts(4, 1, 12)
    assert "4 errors" in strip._errors.text()
    assert "1 warning" in strip._warnings.text()
    assert "1 warnings" not in strip._warnings.text()
    assert "12 incomplete" in strip._outstanding.text()


def test_strip_totals_match_the_app_rail_badge(app_driver, many_issues_path):
    """The strip's totals and the app-rail badge derive from the same
    ``PartitionedIssues`` in ``main_window._refresh_all`` -- they can never
    disagree."""
    d = app_driver
    d.open(many_issues_path)
    errors, warnings, _outstanding = d.diagnostics_strip_counts()
    assert errors + warnings == d.validation_badge_count()


# --- stream headers ----------------------------------------------------


def test_stream_lists_only_non_clean_buckets_with_the_clear_line_naming_the_rest(
    app_driver, many_issues_path
):
    d = app_driver
    d.open(many_issues_path)
    # Cell/Negative electrode/Positive electrode carry errors; Header/State
    # are untouched -- clean buckets never get a header (D3).
    assert d.diagnostics_stream_headers() == [
        "Cell  2 errors",
        "Negative electrode  1 error",
        "Positive electrode  1 error",
    ]
    assert d.diagnostics_clear_line_text() == "2 sections clear"


def test_clear_bucket_shows_no_header(app_driver, many_issues_path):
    """A clean bucket renders no header at all -- not even one with an
    empty suffix (D3): it's on the clear line instead."""
    d = app_driver
    d.open(many_issues_path)
    assert "Header" not in " ".join(d.diagnostics_stream_headers())
    assert "State" not in " ".join(d.diagnostics_stream_headers())


def test_stream_header_suffix_matches_the_bucket(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    cell = d.diagnostics_bucket("Cell")
    assert cell.error_count == 2  # two merged union-pair rows
    assert cell.warning_count == 0
    electrode = d.diagnostics_bucket("Negative electrode")
    assert electrode.error_count == 1


def test_absent_required_section_header_reads_section_absent(app_driver, tmp_path):
    from core import document_factory

    raw = document_factory.create("SPMe", title="probe")
    del raw["Parameterisation"]["Electrolyte"]
    d = app_driver
    d.open(_write(tmp_path, "absent_electrolyte.json", raw))

    assert "Electrolyte  section absent" in d.diagnostics_stream_headers()
    bucket = d.diagnostics_bucket("Electrolyte")
    assert bucket.outstanding_count == 1
    assert bucket.error_count == 0
    # its Outstanding row carries the add-section action, not "Go to ›".
    task_texts = d.diagnostics_stream_task_texts()
    assert any("+ Add section" in text for text in task_texts)


def test_document_bucket_appears_only_when_occupied(app_driver, valid_spm_path, fixtures_dir):
    d = app_driver
    d.open(valid_spm_path)
    assert not any(header.startswith("Document") for header in d.diagnostics_stream_headers())

    d.open(fixtures_dir / "nmc_pouch_cell_BPX.json")
    headers = d.diagnostics_stream_headers()
    assert any(header.startswith("Document") for header in headers)
    # Document sits first, occupied buckets in document order after it.
    assert headers[0].startswith("Document")


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


# --- issue/task rows ----------------------------------------------------


def test_a_section_shows_only_its_own_issue_rows(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)

    texts = d.diagnostics_stream_issue_texts()
    assert len(texts) == 4  # 2 in Cell + 1 in Negative electrode + 1 in Positive electrode
    assert all("Cell" not in text.split(":")[0] for text in texts)


def test_header_owned_issue_shows_in_the_header_section(app_driver, tmp_path, valid_spm_dict):
    """``Parameterisation`` is a structural wrapper stripped for display, but
    ``Header`` is itself a meaningful section and must not be: a bad
    ``Header.Model`` lands in the "Header" bucket, not somewhere else."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Header"]["Model"] = "banana"
    d = app_driver
    d.open(_write(tmp_path, "bad_header.json", raw))

    assert d.diagnostics_bucket("Header").error_count == 1
    assert any(header.startswith("Header") for header in d.diagnostics_stream_headers())


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
    # is muted, the message present, and no bracketed [ERROR] tag survives --
    # a delegate-painted icon carries severity now.
    assert "<br>" in row
    assert "Lower voltage cut-off" in row
    assert "[V]" in row
    assert "Input should be a valid number" in row
    assert "[ERROR]" not in row and "[WARN]" not in row


def test_issue_rows_carry_the_severity_role_for_the_delegate_icon(app_driver, many_issues_path):
    from ui_qt import parameter_row

    d = app_driver
    d.open(many_issues_path)
    severities = {item.data(parameter_row.SEVERITY_ROLE) for item in d._validation_rows("issue")}
    assert severities == {"error", "warning"} or severities == {"error"}
    # this fixture's issues are all errors specifically:
    assert severities == {"error"}


def test_declare_model_only_header_shows_no_ratio(app_driver, tmp_path):
    """DECLARE_MODEL is not itself a section-shape fact -- its header must
    show no outstanding ratio at all (D5/states table)."""
    from core import document_factory

    raw = document_factory.create("SPM", title="probe")
    del raw["Header"]["Model"]
    d = app_driver
    d.open(_write(tmp_path, "no_model.json", raw))

    header = next(h for h in d.diagnostics_stream_headers() if h.startswith("Header"))
    assert "remaining" not in header
    assert " of " not in header


def test_optional_subhead_only_when_optional_tasks_exist(app_driver, tmp_path):
    from core import document_factory

    raw = document_factory.create("SPM", title="probe")
    d = app_driver
    d.open(_write(tmp_path, "no_optional.json", raw))
    assert d.diagnostics_stream_subhead_texts() == []

    raw["Parameterisation"]["Cell"]["Volume [m3]"] = None
    d.open(_write(tmp_path, "with_optional.json", raw))
    subheads = d.diagnostics_stream_subhead_texts()
    assert subheads == ["OPTIONAL . 1 UNFILLED"]


# --- clear line / all-clear / Partial notice --------------------------------


def test_fully_clean_document_shows_the_all_clear_row_and_clear_line(app_driver, valid_spm_path):
    from ui_qt import style

    d = app_driver
    d.open(valid_spm_path)

    assert d.diagnostics_stream_headers() == []
    total = len(d._w._diagnostics._buckets.buckets)
    assert d.diagnostics_all_clear_text() == (
        style.all_clear("No issues, nothing incomplete")
        + f"\n{total} of {total} sections complete and valid"
    )
    assert d.diagnostics_clear_line_text() == f"{total} sections clear"


def test_partial_and_fully_clear_all_clear_row_shows_the_partial_notice_as_line_2(
    app_driver, tmp_path
):
    """Amended D9 (2026-08-05 review finding): under Partial there is no
    completion target, so "N of N sections complete and valid" is a false
    claim even when the page is genuinely error/warning/outstanding-free --
    line 1 (the plain check + "No issues, nothing incomplete") is
    unchanged, but line 2 becomes the Partial notice, and it must not ALSO
    render as its own separate row."""
    from core import document_factory

    from ui_qt import style
    from ui_qt.diagnostics_panel import _MSG_PARTIAL_NO_TARGET

    raw = document_factory.create("Partial", title="probe")
    d = app_driver
    d.open(_write(tmp_path, "partial_clean.json", raw))

    assert d._w._diagnostics._buckets.error_count == 0
    assert d._w._diagnostics._buckets.warning_count == 0
    assert d._w._diagnostics._buckets.outstanding_count == 0

    assert d.diagnostics_all_clear_text() == (
        style.all_clear("No issues, nothing incomplete") + f"\n{_MSG_PARTIAL_NO_TARGET}"
    )
    assert d._validation_rows("message") == []  # not also a separate Partial-notice row


def test_one_error_in_one_section_leaves_the_rest_clear(app_driver, tmp_path, valid_spm_dict):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "banana"
    d = app_driver
    d.open(_write(tmp_path, "one_error.json", raw))

    assert d.diagnostics_stream_headers() == ["Cell  1 error"]
    total = len(d._w._diagnostics._buckets.buckets)
    assert d.diagnostics_clear_line_text() == f"{total - 1} sections clear"


def test_clear_line_expands_to_one_row_per_clear_bucket(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    assert d.diagnostics_clear_section_texts() == []  # collapsed by default

    d.diagnostics_toggle_clear_line()

    texts = d.diagnostics_clear_section_texts()
    assert len(texts) == 2  # Header, State
    assert all(text for text in texts)

    d.diagnostics_toggle_clear_line()
    assert d.diagnostics_clear_section_texts() == []


def test_clear_row_is_html_based_muted_no_accent_and_compact(app_driver, tmp_path, valid_spm_dict):
    """Review finding: the clear line's own rows used to be a bespoke
    custom paint that rendered tall on screen, with accent-tinted digits.
    They now reuse the same HTML-document row machinery every other
    single-line row (e.g. the OPTIONAL sub-head) uses -- D4 pins them as
    "one quiet muted line ... same compact height as other rows" -- proven
    here structurally: the row carries an HTML_ROLE fragment (not the
    deleted bespoke paint path), every colour in it is the muted grey
    (never ACCENT), and its delegate sizeHint matches an ordinary
    HTML-based single-line row's (the OPTIONAL sub-head, computed in this
    same environment so the comparison can't be thrown off by a synthetic
    QStyleOptionViewItem's own font/metrics) -- not the taller banded
    fold-header/clear-line height."""
    from PySide6.QtWidgets import QStyleOptionViewItem

    from ui_qt import parameter_row, style

    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Volume [m3]"] = None  # 1 optional task -> Cell's own subhead
    d = app_driver
    d.open(_write(tmp_path, "clear_row_sizing.json", raw))
    d.diagnostics_toggle_clear_line()

    clear_rows = d._validation_rows("clear_row")
    subheads = d._validation_rows("subhead")
    assert clear_rows  # premise: at least one clear bucket exists
    assert subheads  # premise: at least one known-compact HTML row exists to compare against

    lst = d._w._diagnostics._stream._list
    delegate = lst.itemDelegate()
    option = QStyleOptionViewItem()
    option.font = lst.font()
    for item in clear_rows:
        html = item.data(parameter_row.HTML_ROLE)
        assert html is not None
        assert style.ACCENT not in html
        assert style.MUTED in html

    # Height check on the short, bare-label clear row ("State", whose
    # required_total is 0 -- no ratio to append, see _clear_row_text)
    # against the subhead's own height: both go through the identical
    # HTML-document sizeHint path, so at comparable text length they must
    # land on the same single-line height -- unlike a longer clear row's
    # text, which may legitimately wrap.
    state_row = next(item for item in clear_rows if item.text() == "State")
    subhead_height = delegate.sizeHint(option, lst.indexFromItem(subheads[0])).height()
    state_height = delegate.sizeHint(option, lst.indexFromItem(state_row)).height()
    assert state_height == subhead_height


def test_partial_notice_renders_once_above_the_clear_line_when_nothing_outstanding(
    app_driver, tmp_path
):
    from core import document_factory

    raw = document_factory.create("Partial", title="probe")
    raw["Parameterisation"]["Negative electrode"] = {"Thickness [m]": 1e-4}
    d = app_driver
    d.open(_write(tmp_path, "partial_sparse.json", raw))

    assert d._w._diagnostics._buckets.outstanding_count == 0
    assert d.diagnostics_all_clear_text() is None  # errors exist -- not all-clear
    assert d.diagnostics_stream_task_texts() == []
    from ui_qt.diagnostics_panel import _MSG_PARTIAL_NO_TARGET

    messages = d._validation_rows("message")
    assert len(messages) == 1
    assert messages[0].text() == _MSG_PARTIAL_NO_TARGET


# --- fold + collapse-all ----------------------------------------------------


def test_only_issue_and_task_rows_are_interactive():
    """Headers, sub-heads and messages paint flat -- the delegate strips
    hover/selection for every kind outside this set. A highlight promises
    interaction; activating those rows is a structural no-op."""
    from ui_qt.diagnostics_panel import _DiagnosticsRowDelegate

    assert _DiagnosticsRowDelegate._INTERACTIVE_KINDS == {"issue", "task"}


def test_fold_header_paints_as_a_fixed_height_band(app_driver, many_issues_path):
    """Fold headers get a fixed-height band treatment (the delegate
    overrides sizeHint for them)."""
    from PySide6.QtWidgets import QStyleOptionViewItem

    from ui_qt.diagnostics_panel import _DiagnosticsRowDelegate

    d = app_driver
    d.open(many_issues_path)
    lst = d._w._diagnostics._stream._list
    header = d._validation_rows("fold_header")[0]
    index = lst.indexFromItem(header)
    option = QStyleOptionViewItem()
    option.font = lst.font()
    assert lst.itemDelegate().sizeHint(option, index).height() == _DiagnosticsRowDelegate._FOLD_HEADER_HEIGHT


# --- fold ------------------------------------------------------------------


def test_folding_a_bucket_hides_both_its_issue_and_task_rows(app_driver, tmp_path, valid_spm_dict):
    """Fold is per-bucket (issues + outstanding together). Uses a Cell
    bucket that genuinely carries BOTH an issue (a bad value) and a task (a
    deleted required field), so folding is proved to hide each half of its
    own claim, not just the one a fresh skeleton happens to have."""
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

    d.diagnostics_fold_section("Cell")

    assert ("Cell", True) in d.all_sections_fold_headers()
    assert len(d.validation_issue_texts()) == issues_before - 1
    assert len(d.validation_task_texts()) == tasks_before - 1

    d.diagnostics_fold_section("Cell")
    assert ("Cell", False) in d.all_sections_fold_headers()
    assert len(d.validation_issue_texts()) == issues_before
    assert len(d.validation_task_texts()) == tasks_before


def test_fold_survives_a_refresh(app_driver):
    d = app_driver
    d._w._new("SPM")
    d.diagnostics_fold_section("Cell")
    assert ("Cell", True) in d.all_sections_fold_headers()

    d._w._state.active.apply_value(("Header", "Title"), "still folded")
    d._w._refresh_all()

    assert ("Cell", True) in d.all_sections_fold_headers()


def test_fold_does_not_leak_into_a_new_document(app_driver, monkeypatch):
    d = app_driver
    d._w._new("SPM")
    d.diagnostics_fold_section("Cell")
    assert ("Cell", True) in d.all_sections_fold_headers()

    from ui_qt import main_window as main_window_module

    # take the clean path, then accept its replace confirm
    d._w._state.active.dirty = False
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *a, **k: main_window_module.QMessageBox.Ok,
    )
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
    d.diagnostics_fold_section("Cell")
    assert ("Cell", True) in d.all_sections_fold_headers()

    d.open(other)
    assert ("Cell", False) in d.all_sections_fold_headers()


def test_clear_line_fold_state_and_chips_reset_on_a_new_document(app_driver, many_issues_path, monkeypatch):
    """D11: opening a *different* document resets folds, the clear line and
    the chips -- covers the clear-line half specifically (folds/chips are
    covered elsewhere)."""
    d = app_driver
    d.open(many_issues_path)
    d.diagnostics_toggle_clear_line()
    assert d.diagnostics_clear_section_texts() != []

    from ui_qt import main_window as main_window_module

    # accept the clean-document replace confirm New now shows
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *a, **k: main_window_module.QMessageBox.Ok,
    )
    d._w._new("SPM")

    assert d.diagnostics_clear_section_texts() == []


# --- collapse all / expand all (D15) ----------------------------------------


def test_collapse_all_hidden_with_fewer_than_two_rendered_sections(app_driver, tmp_path, valid_spm_dict):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "banana"
    d = app_driver
    d.open(_write(tmp_path, "one_section.json", raw))

    assert len(d.diagnostics_stream_headers()) == 1
    assert d.diagnostics_collapse_all_text() is None


def test_collapse_all_toggles_every_rendered_section_at_once(app_driver, many_issues_path):
    d = app_driver
    d.open(many_issues_path)
    assert len(d.diagnostics_stream_headers()) == 3
    assert d.diagnostics_collapse_all_text() == "Collapse all"  # all expanded by default

    d.diagnostics_toggle_collapse_all()

    assert all(collapsed for _label, collapsed in d.all_sections_fold_headers())
    assert d.diagnostics_collapse_all_text() == "Expand all"
    assert d.diagnostics_stream_issue_texts() == []  # every section's rows now folded away

    d.diagnostics_toggle_collapse_all()

    assert all(not collapsed for _label, collapsed in d.all_sections_fold_headers())
    assert d.diagnostics_collapse_all_text() == "Collapse all"


def test_collapse_all_from_a_mixed_fold_state_collapses_everything(app_driver, many_issues_path):
    """Starting from one folded, two open sections, the label still reads
    "Collapse all" (something is still expanded) and a click on it does
    exactly that -- collapses every section, the folded one included, not
    a toggle-to-the-opposite-of-most."""
    d = app_driver
    d.open(many_issues_path)
    d.diagnostics_fold_section("Cell")
    assert d.diagnostics_collapse_all_text() == "Collapse all"  # 2 of 3 still open

    d.diagnostics_toggle_collapse_all()

    assert all(collapsed for _label, collapsed in d.all_sections_fold_headers())
    assert d.diagnostics_collapse_all_text() == "Expand all"


def test_collapse_all_label_does_not_go_stale_after_per_header_folds(app_driver, many_issues_path):
    """Review-found regression: folding every rendered section one by one
    via its own header click used to leave the strip label reading
    "Collapse all" forever (``_StreamView._on_clicked`` re-rendered only
    itself, never telling ``DiagnosticsPanel`` to refresh the label) --
    clicking it then EXPANDED everything, the opposite of what the label
    said. Folding every section by hand must flip the label to "Expand
    all", and clicking it from there must expand everything, not collapse
    it further."""
    d = app_driver
    d.open(many_issues_path)
    labels = [label for label, _collapsed in d.all_sections_fold_headers()]
    assert len(labels) == 3  # premise: enough sections to need the affordance at all

    for label in labels:
        d.diagnostics_fold_section(label)

    assert all(collapsed for _label, collapsed in d.all_sections_fold_headers())
    assert d.diagnostics_collapse_all_text() == "Expand all"

    d.diagnostics_toggle_collapse_all()

    assert all(not collapsed for _label, collapsed in d.all_sections_fold_headers())
    assert d.diagnostics_collapse_all_text() == "Collapse all"


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
    """The State-like shape (groups a present section's absent children into
    its own bucket): no leaf fields required, one or more MISSING_SECTION
    children -- reports "N sections absent", never a misleading "0 of 0
    remaining" (the case the confirmed-live bug came from)."""
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


# --- _section_header_suffix / clear line copy (pure functions) -------------


def _bucket2(**overrides):
    """Like ``_bucket`` but also lets error/warning counts vary -- ``_bucket``
    pins both at 0, which every pre-existing ``_ratio_words`` test wants but
    the D5 suffix tests need to vary."""
    from core.page_buckets import SectionBucket

    fields = dict(
        path=("Parameterisation", "Cell"),
        label="Cell",
        absent=False,
        issues=(),
        required_tasks=(),
        optional_tasks=(),
        required_total=0,
        error_count=0,
        warning_count=0,
    )
    fields.update(overrides)
    return SectionBucket(**fields)


def test_section_header_suffix_error_and_warning_and_ratio():
    from ui_qt.diagnostics_panel import _section_header_suffix

    assert _section_header_suffix(_bucket2(error_count=1)) == "1 error"
    assert _section_header_suffix(_bucket2(warning_count=3)) == "3 warnings"
    assert _section_header_suffix(_bucket2(error_count=1, warning_count=2)) == "1 error · 2 warnings"
    assert _section_header_suffix(_bucket2()) == ""  # a clear bucket has no suffix at all


def test_section_header_suffix_includes_the_outstanding_ratio():
    from core.completion import CompletionTask, TaskKind
    from ui_qt.diagnostics_panel import _section_header_suffix

    task = CompletionTask(kind=TaskKind.MISSING_FIELD, path=("Parameterisation", "Cell", "X"), alias="X", required=True)
    bucket = _bucket2(error_count=1, required_tasks=(task,), required_total=5)
    assert _section_header_suffix(bucket) == "1 error · 1 of 5 remaining"


def test_section_header_suffix_omits_the_ratio_for_declare_model_only():
    from core.completion import CompletionTask, TaskKind
    from ui_qt.diagnostics_panel import _section_header_suffix

    task = CompletionTask(kind=TaskKind.DECLARE_MODEL, path=("Header", "Model"), alias="Model", required=True)
    bucket = _bucket2(path=("Header",), label="Header", required_tasks=(task,), required_total=2)
    assert _section_header_suffix(bucket) == ""


def test_clear_row_text_present_bucket_with_a_known_total():
    from ui_qt.diagnostics_panel import _clear_row_text

    assert _clear_row_text(_bucket(required_total=5)) == "Cell · 5 of 5 filled"


def test_clear_row_text_present_bucket_without_a_ratio():
    from ui_qt.diagnostics_panel import _clear_row_text

    assert _clear_row_text(_bucket(label="Document", required_total=None)) == "Document"
    assert _clear_row_text(_bucket(label="Header", required_total=0)) == "Header"


def test_clear_row_text_absent_bucket():
    """The "Absent optional section, nothing outstanding" state (states
    table): unreachable through a real document today -- an absent
    schema-optional section generates no MISSING_SECTION task and so never
    becomes a bucket at all (core.page_buckets._bucket_order's three passes
    only ever introduce an absent bucket via a required-section task) --
    covered directly on the pure function instead."""
    from ui_qt.diagnostics_panel import _clear_row_text

    assert _clear_row_text(_bucket(label="Electrolyte", absent=True, required_total=None)) == (
        "Electrolyte · section absent"
    )


def test_clear_line_text_singular_and_plural():
    from ui_qt.diagnostics_panel import _clear_line_text

    assert _clear_line_text(1) == "1 section clear"
    assert _clear_line_text(2) == "2 sections clear"


# --- pinned regressions found by driving the real (non-offscreen) app ------
#
# Right-aligned task-row action text, bordered summary-strip chips, and the
# fold chevron glyph.


def test_task_row_action_text_is_a_separate_right_aligned_role(app_driver):
    """REQUIRED sits inline after the name; the action text is painted
    separately, right-aligned, in accent colour -- not folded into the same
    parenthetical the way it used to render ("Name (REQUIRED . Go to >)")."""
    from ui_qt import diagnostics_panel as dp
    from ui_qt import parameter_row

    d = app_driver
    d._w._new("SPM")
    lst = d._w._diagnostics._stream._list
    task_item = next(lst.item(i) for i in range(lst.count()) if lst.item(i).data(dp._KIND_ROLE) == "task")

    assert task_item.data(parameter_row.ACTION_ROLE) == "Go to ›"
    html = task_item.data(parameter_row.HTML_ROLE)
    assert "REQUIRED" in html
    assert "Go to" not in html  # action text lives in ACTION_ROLE, not the HTML fragment
    assert "· Go to ›" not in task_item.text()  # plain text no longer parenthesises it with REQUIRED


def test_summary_strip_chips_are_bordered_boxes(app_driver, valid_spm_path):
    """The wireframe calls for "boxes/shading to make regions distinguishable"
    -- plain coloured text is not enough; each chip must be its own
    QSS-styled card."""
    d = app_driver
    d.open(valid_spm_path)
    strip = d._w._diagnostics._strip
    for chip in (strip._errors, strip._warnings, strip._outstanding):
        assert chip.objectName() == "DiagnosticsChip"


def test_fold_header_glyph_flips_with_collapsed_state(app_driver):
    """The chevron glyph flips correctly with fold state (this pins the
    plain-text half of that against regression -- the delegate's own
    painted chevron is computed from the same collapsed flag, see
    _DiagnosticsRowDelegate._paint_fold_header)."""
    from ui_qt import diagnostics_panel as dp

    d = app_driver
    d._w._new("SPM")
    header = next(item for item in d._validation_rows("fold_header") if item.data(dp._FOLD_BUCKET_ROLE).label == "Cell")
    assert header.text().startswith("▾")

    d.diagnostics_fold_section("Cell")
    header = next(item for item in d._validation_rows("fold_header") if item.data(dp._FOLD_BUCKET_ROLE).label == "Cell")
    assert header.text().startswith("▸")


# --- flat dots, tooltips, crisper boxes -------------------------------------


def test_task_row_tooltip_is_task_kind_derived(app_driver):
    """Drift-safe: the tooltip is looked up from the task's own ``kind``
    enum via ``style.task_kind_tooltip`` -- never from its alias/path text."""
    from core.completion import TaskKind
    from ui_qt import diagnostics_panel as dp
    from ui_qt import style

    d = app_driver
    d._w._new("SPM")
    lst = d._w._diagnostics._stream._list
    task_item = next(lst.item(i) for i in range(lst.count()) if lst.item(i).data(dp._KIND_ROLE) == "task")
    task = task_item.data(dp._TASK_ROLE)

    assert task.kind is TaskKind.MISSING_FIELD  # a fresh Cell skeleton's tasks are all missing fields
    assert task_item.toolTip() == style.task_kind_tooltip(task.kind)


def test_strip_chip_tooltips_reflect_counts_and_say_they_filter(app_driver, many_issues_path):
    """Counts stay truthful (F8), and the suffix is the one place the chips
    admit to being click-to-filter toggles -- including the off state."""
    from ui_qt import style

    d = app_driver
    d.open(many_issues_path)
    strip = d._w._diagnostics._strip
    errors, warnings, outstanding = d.diagnostics_strip_counts()

    assert strip._errors.toolTip() == f"{style.error_count_tooltip(errors)} · click to hide"
    assert strip._warnings.toolTip() == f"{style.warning_count_tooltip(warnings)} · click to hide"
    assert (
        strip._outstanding.toolTip()
        == f"{style.outstanding_count_tooltip(outstanding)} · click to hide"
    )

    strip._errors.set_on(False)
    strip._on_chip_toggled(False)
    assert (
        strip._errors.toolTip()
        == f"{style.error_count_tooltip(errors)} · hidden · click to show"
    )


def test_severity_dots_carry_no_inner_glyph_text_in_the_delegate(app_driver, many_issues_path):
    """The delegate paints a flat dot, not an icon-in-circle. Structural
    proof (paint is a no-op to assert against directly): the delegate's
    severity-icon painter no longer draws any glyph text -- inspect its
    source rather than pixels, since colour-only circle painting is already
    covered by test_activity_bar.py-style pixel probes elsewhere in this
    suite for the equivalent badge pattern."""
    from ui_qt.parameter_row import ParameterRowDelegate

    import inspect

    source = inspect.getsource(ParameterRowDelegate._paint_severity_icon)
    assert "drawText" not in source
    assert "✕" not in source and '"!"' not in source


def test_task_glyph_is_muted_grey_not_bold(app_driver):
    """A task row's ring/half-filled mark must render in the same grey
    (#57606a) family as the issue dots -- the shared dot family, rendered
    muted rather than swept into the bold name span the way a text glyph
    used to be."""
    from ui_qt import diagnostics_panel as dp
    from ui_qt import icons, parameter_row, style

    d = app_driver
    d._w._new("SPM")
    lst = d._w._diagnostics._stream._list
    task_item = next(lst.item(i) for i in range(lst.count()) if lst.item(i).data(dp._KIND_ROLE) == "task")
    html = task_item.data(parameter_row.HTML_ROLE)
    task = task_item.data(dp._TASK_ROLE)

    expected_glyph = icons.html_img(dp._task_glyph_svg(task), color=style.MUTED, size=parameter_row.MARK_BOX)
    assert html.startswith(expected_glyph)
