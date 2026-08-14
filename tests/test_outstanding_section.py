"""Diagnostics page Outstanding section: absorption, the activity-bar badge,
and Outstanding row activation dispatch.

Walks four document states end to end through the real MainWindow (state 1:
fresh skeleton; state 2: a working document with one visible error plus
outstanding work; state 3: Partial with a sparse electrode; state 4: a
complete, untouched document), then covers the polymorphic Outstanding
activation contract and the structural non-activatable rows.

Two mutation-sensitive seams are verified by hand rather than as an
automated test (a pytest run cannot revert production code mid test): (a)
the badge must derive from POST-absorption counts, and (b) the
AddSection -> Outstanding re-render cascade must actually run.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from explore_bpx.core import document_factory
from explore_bpx.core.completion import TaskKind

_CELL = ("Parameterisation", "Cell")
_CAPACITY = _CELL + ("Nominal cell capacity [A.h]",)
_LOWER_CUTOFF = _CELL + ("Lower voltage cut-off [V]",)


def _write(tmp_path, name: str, raw: dict):
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _skeleton_path(tmp_path):
    return _write(tmp_path, "skeleton.json", document_factory.create("SPM", title="probe"))


def _working_doc_path(tmp_path, valid_spm_dict):
    """State 2: a malformed Header.BPX string, one required field deleted,
    one required field committed null."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Header"]["BPX"] = "not-a-version"
    del raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = None
    return _write(tmp_path, "working.json", raw)


def _partial_sparse_electrode_path(tmp_path):
    raw = document_factory.create("Partial", title="probe")
    raw["Parameterisation"]["Negative electrode"] = {"Thickness [m]": 1e-4}
    return _write(tmp_path, "partial.json", raw)


def _undeclared_model_path(tmp_path):
    raw = document_factory.create("SPM", title="probe")
    del raw["Header"]["Model"]
    return _write(tmp_path, "no_model.json", raw)


# ---------------------------------------------------------------------------
# State 1 -- fresh skeleton: calm badge, State group renders, N-of-M headers.
# ---------------------------------------------------------------------------


def test_state1_fresh_skeleton(app_driver, tmp_path):
    d = app_driver
    d.open(_skeleton_path(tmp_path))

    assert d.validation_issue_count() == 0
    assert d.diagnostics_filter_counts() == (0, 0, 5 + 9 + 9)
    assert d.validation_badge_count() == 0
    assert d.validation_badge_severity() is None

    headers = d.diagnostics_stream_headers()
    assert "Cell  5 of 5 remaining" in headers
    assert "Negative electrode  9 of 9 remaining" in headers
    assert "Positive electrode  9 of 9 remaining" in headers
    # bpx 1.1.1 made `State` schema-optional (Field(None, alias="State")) and
    # deleted the root validator that used to demand it, so `document_factory`
    # no longer scaffolds it at all -- there is no State header here.
    assert not any(header.startswith("State") for header in headers)
    assert d.validation_outstanding_count() == 5 + 9 + 9
    tasks = d.outstanding_tasks()
    assert not any(t.path[:1] == ("State",) for t in tasks)
    # Tree-dot consistency: a fresh skeleton's tree is as calm as its badge
    # -- required-but-absent fields are outstanding, not red.
    assert d.tree_error_marked_sections() == []


# ---------------------------------------------------------------------------
# State 2 -- working document: one visible BPX-pattern error, two Outstanding
# rows (a missing field, a null field), badge counts exactly one error.
# ---------------------------------------------------------------------------


def test_state2_working_document(app_driver, tmp_path, valid_spm_dict):
    d = app_driver
    d.open(_working_doc_path(tmp_path, valid_spm_dict))

    assert d.validation_issue_count() == 1
    assert "BPX" in d.validation_issue_texts()[0]
    assert d.validation_badge_count() == 1
    assert d.validation_badge_severity() == "error"

    tasks = d.outstanding_tasks()
    assert any(t.kind is TaskKind.MISSING_FIELD and t.path == _CAPACITY for t in tasks)
    assert any(t.kind is TaskKind.NULL_FIELD and t.path == _LOWER_CUTOFF for t in tasks)
    headers = d.diagnostics_stream_headers()
    assert "Cell  2 of 5 remaining" in headers

    # Tree-dot consistency: Cell's missing/null fields are outstanding, so
    # Cell stays calm in the tree as in the badge. The one
    # genuine error here shows no dot either -- the malformed-BPX diagnostic
    # attaches to the document root (nav ``()``), which has no tree row; the
    # badge and the Document bucket carry it (unchanged from the verbatim-era
    # tree, which equally never surfaced root-attached issues).
    assert d.tree_error_marked_sections() == []


def test_state2b_bad_value_marks_its_section_in_the_tree(app_driver, tmp_path, valid_spm_dict):
    """The positive half of tree-dot consistency: a genuinely wrong value
    (not emptiness) keeps its section's red dot, on that section alone."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = []
    d = app_driver
    d.open(_write(tmp_path, "bad_value.json", raw))

    assert d.validation_badge_severity() == "error"
    assert d.tree_error_marked_sections() == [("Parameterisation", "Cell")]


# ---------------------------------------------------------------------------
# State 3 -- Partial + sparse electrode: the union missing errors stay
# visible (safety net), Outstanding shows the Partial notice, badge is 8.
# ---------------------------------------------------------------------------


def test_state3_partial_sparse_electrode(app_driver, tmp_path):
    d = app_driver
    d.open(_partial_sparse_electrode_path(tmp_path))

    assert d.validation_issue_count() == 8
    assert d.validation_badge_count() == 8
    assert d.validation_badge_severity() == "error"
    assert d.outstanding_tasks() == []

    # The Partial notice is page-scoped now (a bucket alone can't tell
    # "Partial" from "fully complete" -- see diagnostics_panel._MSG_PARTIAL_
    # NO_TARGET): one pinned row, rendered once, whenever nothing is
    # outstanding anywhere on the page under Partial.
    assert d._w._diagnostics._buckets.outstanding_count == 0
    messages = d._validation_rows("message")
    assert len(messages) == 1
    notice = messages[0].text()
    assert notice == (
        "Model is Partial, so there is no completion target. Expected "
        "fields are still suggested in each section's parameter list."
    )
    # Terminology discipline: "valid"/"invalid" never appear in the
    # Outstanding notice.
    assert "valid" not in notice.lower()
    assert "invalid" not in notice.lower()


def test_state3b_partial_null_is_outstanding_not_error(app_driver, tmp_path, valid_spm_dict):
    """A committed null under Partial is outstanding work, not a red error --
    the same calm treatment a concrete model gives it. The motivating
    scenario: a complete document flipped to Partial with one field emptied
    used to go red everywhere (row dot, tree dot, badge) while the identical
    SPM document stayed calm. The Partial notice is page-scoped and only
    renders when NOTHING is outstanding anywhere -- since this document
    does have one NULL_FIELD task, the notice is absent entirely (a real
    task row is a strictly more useful answer than the generic notice)."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Header"]["Model"] = "Partial"
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = None
    d = app_driver
    d.open(_write(tmp_path, "partial_null.json", raw))

    assert d.validation_issue_count() == 0
    assert d.validation_badge_count() == 0
    assert d.validation_badge_severity() is None

    tasks = d.outstanding_tasks()
    assert [t.kind for t in tasks] == [TaskKind.NULL_FIELD]
    assert tasks[0].path == _CAPACITY
    assert tasks[0].required is False  # nothing is Required under Partial
    assert d.diagnostics_stream_subhead_texts() == ["1 optional parameter unfilled"]
    assert d.tree_error_marked_sections() == []  # calm tree too

    cell_header = next(h for h in d.diagnostics_stream_headers() if h.startswith("Cell"))
    assert "of" not in cell_header
    assert "remaining" not in cell_header
    assert "capacity" in " ".join(d.diagnostics_stream_task_texts()).lower()
    assert d._validation_rows("message") == []  # the page-wide Partial notice does not render


# ---------------------------------------------------------------------------
# State 4 -- done: an untouched valid document shows both empty states and a
# clear badge.
# ---------------------------------------------------------------------------


def test_state4_done(app_driver, valid_spm_path):
    from explore_bpx.ui_qt import style

    d = app_driver
    d.open(valid_spm_path)

    assert d.diagnostics_filter_counts() == (0, 0, 0)
    assert d.diagnostics_stream_headers() == []
    total = len(d._w._diagnostics._buckets.buckets)
    assert d.diagnostics_all_clear_text() == (
        style.all_clear("No issues, nothing incomplete") + f"\n{total} of {total} sections complete and valid"
    )
    assert d.validation_badge_count() == 0
    assert d.validation_badge_severity() is None


# ---------------------------------------------------------------------------
# Activation dispatch, each through the real driver.
# ---------------------------------------------------------------------------


def test_missing_field_activation_reveals_the_fields_to_add_group(app_driver, tmp_path, valid_spm_dict):
    d = app_driver
    d.open(_working_doc_path(tmp_path, valid_spm_dict))
    task = next(t for t in d.outstanding_tasks() if t.kind is TaskKind.MISSING_FIELD and t.path == _CAPACITY)

    d.activate_outstanding_task(task)

    assert d.tree_selection_label() == "Cell"
    # The group is expanded (Nominal cell capacity plus whatever optional
    # fields the fixture's Cell also omits -- the group is all-Expected, not
    # Required-only) and the missing field is highlighted.
    assert d.fields_to_add_header_text().startswith("▾")
    assert "Nominal cell capacity [A.h]" in d.fields_to_add_suggestion_aliases()
    assert d.fields_to_add_current_alias() == "Nominal cell capacity [A.h]"


def test_null_field_activation_selects_the_parameter(app_driver, tmp_path, valid_spm_dict):
    d = app_driver
    d.open(_working_doc_path(tmp_path, valid_spm_dict))
    task = next(t for t in d.outstanding_tasks() if t.kind is TaskKind.NULL_FIELD and t.path == _LOWER_CUTOFF)

    d.activate_outstanding_task(task)

    assert d.shown_parameter_path() == _LOWER_CUTOFF
    assert d.inspector_title() == "Lower voltage cut-off [V]"


def test_missing_section_activation_adds_and_cascades_end_to_end(app_driver, tmp_path):
    """The full cascade, end to end: activating an absent section's
    Outstanding row adds it (one undo step) and navigates into it, and the
    Outstanding list immediately enumerates the new section's own required
    fields.

    bpx 1.1.1 made every one of ``State``'s own children schema-optional too
    (probed directly: none of ``Initial conditions``/``Thermal environment``/
    ``Degradation`` are in ``State``'s own JSON-schema ``"required"`` list
    any more), so no
    ``MISSING_SECTION`` task can ever be generated for them -- there is no
    remaining nested required section anywhere in the schema to demonstrate
    this with. ``Parameterisation`` -> ``Electrolyte`` (required for SPMe)
    exercises the same cascade mechanism one level up instead.
    """
    d = app_driver
    raw = document_factory.create("SPMe", title="probe")
    del raw["Parameterisation"]["Electrolyte"]
    d.open(_write(tmp_path, "spme_no_electrolyte.json", raw))
    electrolyte_path = ("Parameterisation", "Electrolyte")
    task = next(t for t in d.outstanding_tasks() if t.kind is TaskKind.MISSING_SECTION and t.path == electrolyte_path)
    assert d.undo_enabled() is False

    d.activate_outstanding_task(task)

    assert d.undo_enabled() is True  # exactly one undo step
    assert d.tree_selection_label() == "Electrolyte"
    tasks_after = d.outstanding_tasks()
    assert not any(t.kind is TaskKind.MISSING_SECTION and t.path == electrolyte_path for t in tasks_after)
    assert any(
        t.kind is TaskKind.MISSING_FIELD and t.path == electrolyte_path + ("Cation transference number",)
        for t in tasks_after
    )
    assert any(
        t.kind is TaskKind.MISSING_FIELD and t.path == electrolyte_path + ("Diffusivity [m2.s-1]",) for t in tasks_after
    )

    # Undo reverts both the section AND the Outstanding re-render.
    d.undo()

    assert d.undo_enabled() is False
    tasks_undone = d.outstanding_tasks()
    assert any(t.kind is TaskKind.MISSING_SECTION and t.path == electrolyte_path for t in tasks_undone)
    assert not any(t.path[:2] == electrolyte_path and len(t.path) > 2 for t in tasks_undone)


def test_declare_model_task_renders_standalone_with_no_group_header(app_driver, tmp_path):
    """DECLARE_MODEL is not itself a section-shape fact -- "Header -- 1 of 2
    remaining" read indirectly when the one actionable thing is declaring a
    model. It renders standalone under the Outstanding page header, with no
    group subheader at all (unlike every other task kind, which keeps its
    own/owning-section group)."""
    d = app_driver
    d.open(_undeclared_model_path(tmp_path))

    assert d.validation_group_headers() == []
    tasks = d.outstanding_tasks()
    assert len(tasks) == 1
    assert tasks[0].kind is TaskKind.DECLARE_MODEL


def test_declare_model_activation_navigates_to_header_when_model_absent(app_driver, tmp_path):
    """``Header.Model`` entirely absent: there is no committed parameter, but
    Header's own "fields to add" suggestion row survives the model gate
    (Header's fields don't depend on the model -- see
    ``_append_missing_fields_group``), so activation navigates to Header and
    reveals/selects the Model suggestion row via ``reveal_missing_alias``."""
    d = app_driver
    d.open(_undeclared_model_path(tmp_path))
    tasks = d.outstanding_tasks()
    assert len(tasks) == 1  # exactly one task: declare a model
    assert tasks[0].kind is TaskKind.DECLARE_MODEL

    d.activate_outstanding_task(tasks[0])

    assert d.tree_selection_label() == "Header"
    assert d.fields_to_add_current_alias() == "Model"


def test_declare_model_activation_reveals_fields_to_add_group_and_commits_a_model(app_driver, tmp_path):
    """End to end: ``Header`` present, ``Header.Model`` absent. Activating the
    DECLARE_MODEL Outstanding row must not just navigate to Header -- it must
    reveal a *usable* Header "fields to add" group (the regression this fix
    covers), and the revealed Model suggestion row must be a real path into
    the enum card that can commit a model."""
    d = app_driver
    d.open(_undeclared_model_path(tmp_path))
    tasks = d.outstanding_tasks()
    assert len(tasks) == 1
    assert tasks[0].kind is TaskKind.DECLARE_MODEL

    d.activate_outstanding_task(tasks[0])

    assert d.tree_selection_label() == "Header"
    assert d.fields_to_add_header_text() is not None
    assert d.fields_to_add_current_alias() == "Model"

    d.click_fields_to_add_suggestion("Model")
    assert d.inspector_title() == "Model"
    assert d.editor_kind() == "EnumCard"
    assert d.card_is_editable() is True

    d.edit_field("SPM")
    d.commit()

    assert d.field_value() == "SPM"


def test_declare_model_activation_navigates_to_the_parameter_when_model_unrecognised(
    app_driver, tmp_path, valid_spm_dict
):
    """``Header.Model`` present but not one of SPM/SPMe/DFN/Partial: a real
    committed parameter, so activation navigates straight to it like any
    other parameter -- it is editable via the normal enum card from there."""
    d = app_driver
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Header"]["Model"] = "Mystery"
    d.open(_write(tmp_path, "garbage_model.json", raw))
    tasks = d.outstanding_tasks()
    assert len(tasks) == 1
    assert tasks[0].kind is TaskKind.DECLARE_MODEL

    d.activate_outstanding_task(tasks[0])

    assert d.shown_parameter_path() == ("Header", "Model")
    assert d.inspector_title() == "Model"


# ---------------------------------------------------------------------------
# Structural rows: section headers and group subheaders are non-activatable.
# ---------------------------------------------------------------------------


def test_optional_null_field_gets_its_own_subgroup(app_driver, tmp_path):
    """The confirmed defect: a fresh SPM skeleton plus Cell's optional
    ``Volume [m3]`` added empty used to render "Cell -- 5 of 5 remaining"
    with 6 rows underneath. The optional null now moves to a separate,
    quiet sub-group beneath the required one."""
    raw = document_factory.create("SPM", title="probe")
    raw["Parameterisation"]["Cell"]["Volume [m3]"] = None
    d = app_driver
    d.open(_write(tmp_path, "optional_null_cell.json", raw))

    headers = d.diagnostics_stream_headers()
    assert "Cell  5 of 5 remaining" in headers
    assert d.diagnostics_stream_subhead_texts() == ["1 optional parameter unfilled"]
    assert d.validation_task_row_count_under_header("Cell  5 of 5 remaining") == 5

    optional_task = next(t for t in d.outstanding_tasks() if t.path == _CELL + ("Volume [m3]",))
    assert optional_task.required is False
    row_text = d.outstanding_task_row_text(optional_task)
    assert "REQUIRED" not in row_text
    assert "No Value" in row_text


def test_required_group_ratio_integrity_with_mixed_required_and_optional_tasks(app_driver, tmp_path):
    """The required group's stated N always equals the row count directly
    beneath it, in a section holding BOTH required-missing and
    optional-null tasks together (the scenario that used to read "5 of 5"
    over 6 rows)."""
    raw = document_factory.create("SPM", title="probe")
    raw["Parameterisation"]["Cell"]["Volume [m3]"] = None
    d = app_driver
    d.open(_write(tmp_path, "ratio_integrity.json", raw))

    assert d.validation_task_row_count_under_header("Cell  5 of 5 remaining") == 5


def test_section_with_only_optional_nulls_shows_a_bare_header(app_driver, tmp_path, valid_spm_dict):
    """A section whose only outstanding work is optional gets no ratio at
    all in its header (a bare label) -- ``required_tasks`` is empty, so
    there is no REQUIRED count to report; showing "0 of N remaining" would
    falsely imply N fields are missing when none are (see
    diagnostics_panel._section_header_suffix's own docstring)."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Header"]["Description"] = None
    d = app_driver
    d.open(_write(tmp_path, "only_optional_header.json", raw))

    headers = d.diagnostics_stream_headers()
    assert "Header" in headers  # bare label, no suffix
    assert not any(h.startswith("Header ") for h in headers)  # no trailing ratio words
    assert d.diagnostics_stream_subhead_texts() == ["1 optional parameter unfilled"]


def test_fold_headers_are_non_activatable(app_driver, tmp_path):
    """One foldable header per rendered bucket in the stream; a single
    click folds/unfolds (covered elsewhere), Enter/double-click is a
    structural no-op."""
    d = app_driver
    d.open(_skeleton_path(tmp_path))
    assert d.all_sections_fold_headers()  # premise: at least one bucket renders

    received = []
    d._w._diagnostics.issue_activated.connect(received.append)
    d._w._diagnostics.task_activated.connect(received.append)

    d.activate_fold_header(0)

    assert received == []


def test_group_subheaders_are_non_activatable(app_driver, tmp_path):
    raw = document_factory.create("SPM", title="probe")
    raw["Parameterisation"]["Cell"]["Volume [m3]"] = None
    d = app_driver
    d.open(_write(tmp_path, "subhead_premise.json", raw))
    assert d.diagnostics_stream_subhead_texts()  # premise: at least one sub-head exists

    received = []
    d._w._diagnostics.issue_activated.connect(received.append)
    d._w._diagnostics.task_activated.connect(received.append)

    d.activate_validation_group_header(0)

    assert received == []
