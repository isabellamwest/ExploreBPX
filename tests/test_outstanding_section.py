"""Diagnostics page Outstanding section: absorption, the rail badge, and
Outstanding row activation dispatch (completion track Phase 5 -- decisions
E/F/G/L; PLAN-completion-track.md SS4 Phase 5).

Walks the plan's four mockup states end to end through the real MainWindow
(state 1: fresh skeleton; state 2: a working document with one visible error
plus outstanding work; state 3: Partial with a sparse electrode; state 4: a
complete, untouched document), then covers the polymorphic Outstanding
activation contract (decision L) and the structural non-activatable rows.

Two mutation-sensitive seams the plan calls out are verified by hand rather
than as an automated test (a pytest run cannot revert production code mid
test): (a) the badge must derive from POST-absorption counts, and (b) the V7
cascade (AddSection -> Outstanding re-render) must actually run. Evidence for
both is reported in the implementation summary, not here.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from core import completion, document_factory
from core.completion import TaskKind

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
    assert d.diagnostics_strip_counts() == (0, 0, 5 + 9 + 9)
    assert d.validation_badge_count() == 0
    assert d.validation_badge_severity() is None

    headers = d.validation_group_headers()
    assert "Cell — 5 of 5 remaining" in headers
    assert "Negative electrode — 9 of 9 remaining" in headers
    assert "Positive electrode — 9 of 9 remaining" in headers
    # bpx 1.1.1 made `State` schema-optional (Field(None, alias="State")) and
    # deleted the root validator that used to demand it, so `document_factory`
    # no longer scaffolds it at all -- there is no State group here.
    assert not any(header.startswith("State") for header in headers)
    assert d.validation_outstanding_count() == 5 + 9 + 9
    tasks = d.outstanding_tasks()
    assert not any(t.path[:1] == ("State",) for t in tasks)


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
    assert any(
        t.kind is TaskKind.MISSING_FIELD and t.path == _CAPACITY for t in tasks
    )
    assert any(t.kind is TaskKind.NULL_FIELD and t.path == _LOWER_CUTOFF for t in tasks)
    headers = d.validation_group_headers()
    assert "Cell — 2 of 5 remaining" in headers


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

    # The Partial notice is section-scoped now (a bucket alone can't tell
    # "Partial" from "fully complete" -- see diagnostics_panel._MSG_PARTIAL_
    # NO_TARGET); select the sparse electrode itself and read its box.
    d.diagnostics_select_rail("Negative electrode")
    notice = d.diagnostics_section_outstanding_empty_text()
    assert notice == (
        "Model is Partial — no completion target. Expected fields are "
        "still suggested in each section's parameter list."
    )
    # Terminology discipline (decision B): "valid"/"invalid" never appear in
    # the Outstanding notice.
    assert "valid" not in notice.lower() and "invalid" not in notice.lower()


# ---------------------------------------------------------------------------
# State 4 -- done: an untouched valid document shows both empty states and a
# clear badge.
# ---------------------------------------------------------------------------


def test_state4_done(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)

    assert d.diagnostics_strip_counts() == (0, 0, 0)
    d.diagnostics_select_rail("Header")
    assert d.diagnostics_section_issues_empty_text() == "✓ No issues"
    assert d.diagnostics_section_outstanding_empty_text() == "✓ Nothing outstanding"
    assert d.validation_badge_count() == 0
    assert d.validation_badge_severity() is None


# ---------------------------------------------------------------------------
# Activation dispatch (decision L), each through the real driver.
# ---------------------------------------------------------------------------


def test_missing_field_activation_reveals_the_fields_to_add_group(
    app_driver, tmp_path, valid_spm_dict
):
    d = app_driver
    d.open(_working_doc_path(tmp_path, valid_spm_dict))
    task = next(
        t for t in d.outstanding_tasks() if t.kind is TaskKind.MISSING_FIELD and t.path == _CAPACITY
    )

    d.activate_outstanding_task(task)

    assert d.tree_selection_label() == "Cell"
    # The group is expanded (Nominal cell capacity plus whatever optional
    # fields the fixture's Cell also omits -- decision H's group is
    # all-Expected, not Required-only) and the missing field is highlighted.
    assert d.fields_to_add_header_text().startswith("▾")
    assert "Nominal cell capacity [A.h]" in d.fields_to_add_suggestion_aliases()
    assert d.fields_to_add_current_alias() == "Nominal cell capacity [A.h]"


def test_null_field_activation_selects_the_parameter(app_driver, tmp_path, valid_spm_dict):
    d = app_driver
    d.open(_working_doc_path(tmp_path, valid_spm_dict))
    task = next(
        t for t in d.outstanding_tasks() if t.kind is TaskKind.NULL_FIELD and t.path == _LOWER_CUTOFF
    )

    d.activate_outstanding_task(task)

    assert d.shown_parameter_path() == _LOWER_CUTOFF
    assert d.inspector_title() == "Lower voltage cut-off [V]"


def test_missing_section_activation_adds_and_cascades_end_to_end(app_driver, tmp_path):
    """V7's cascade, end to end: activating an absent section's Outstanding
    row adds it (one undo step) and navigates into it, and the Outstanding
    list immediately enumerates the new section's own required fields.

    Re-baselined for bpx 1.1.1: this used to exercise a doubly-nested case
    (``State`` -> ``Thermal environment``), but bpx 1.1.1 made every one of
    ``State``'s own children schema-optional too (probed directly: none of
    ``Initial conditions``/``Thermal environment``/``Degradation`` are in
    ``State``'s own JSON-schema ``"required"`` list any more), so no
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
    task = next(
        t
        for t in d.outstanding_tasks()
        if t.kind is TaskKind.MISSING_SECTION and t.path == electrolyte_path
    )
    assert d.undo_enabled() is False

    d.activate_outstanding_task(task)

    assert d.undo_enabled() is True  # exactly one undo step
    assert d.tree_selection_label() == "Electrolyte"
    tasks_after = d.outstanding_tasks()
    assert not any(
        t.kind is TaskKind.MISSING_SECTION and t.path == electrolyte_path for t in tasks_after
    )
    assert any(
        t.kind is TaskKind.MISSING_FIELD
        and t.path == electrolyte_path + ("Cation transference number",)
        for t in tasks_after
    )
    assert any(
        t.kind is TaskKind.MISSING_FIELD and t.path == electrolyte_path + ("Diffusivity [m2.s-1]",)
        for t in tasks_after
    )

    # Test 8: undo reverts both the section AND the Outstanding re-render.
    d.undo()

    assert d.undo_enabled() is False
    tasks_undone = d.outstanding_tasks()
    assert any(t.kind is TaskKind.MISSING_SECTION and t.path == electrolyte_path for t in tasks_undone)
    assert not any(t.path[:2] == electrolyte_path and len(t.path) > 2 for t in tasks_undone)


def test_declare_model_task_renders_standalone_with_no_group_header(app_driver, tmp_path):
    """O1 (review fix): DECLARE_MODEL is not itself a section-shape fact --
    "Header -- 1 of 2 remaining" read indirectly when the one actionable
    thing is declaring a model. It renders standalone under the Outstanding
    page header, with no group subheader at all (unlike every other task
    kind, which keeps its own/owning-section group)."""
    d = app_driver
    d.open(_undeclared_model_path(tmp_path))

    assert d.validation_group_headers() == []
    tasks = d.outstanding_tasks()
    assert len(tasks) == 1
    assert tasks[0].kind is TaskKind.DECLARE_MODEL


def test_declare_model_activation_navigates_to_header_when_model_absent(app_driver, tmp_path):
    """``Header.Model`` entirely absent: there is no committed parameter, but
    Header's own "fields to add" suggestion row survives decision C's
    model gate (Header's fields don't depend on the model -- see
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


def test_declare_model_activation_reveals_fields_to_add_group_and_commits_a_model(
    app_driver, tmp_path
):
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
    """The live-review defect, fixed (decision R): a fresh SPM skeleton plus
    Cell's optional ``Volume [m3]`` added empty used to render "Cell -- 5 of
    5 remaining" with 6 rows underneath. The optional null now moves to a
    separate, quiet sub-group beneath the required one."""
    raw = document_factory.create("SPM", title="probe")
    raw["Parameterisation"]["Cell"]["Volume [m3]"] = None
    d = app_driver
    d.open(_write(tmp_path, "optional_null_cell.json", raw))

    headers = d.validation_group_headers()
    assert "Cell — 5 of 5 remaining" in headers
    assert "Cell · optional — 1 unfilled" in headers
    assert d.validation_task_row_count_under_header("Cell — 5 of 5 remaining") == 5

    optional_task = next(
        t for t in d.outstanding_tasks() if t.path == _CELL + ("Volume [m3]",)
    )
    assert optional_task.required is False
    row_text = d.outstanding_task_row_text(optional_task)
    assert "REQUIRED" not in row_text
    assert "added, no value yet" in row_text


def test_required_group_ratio_integrity_with_mixed_required_and_optional_tasks(
    app_driver, tmp_path
):
    """Decision R's exact promise: the required group's stated N always
    equals the row count directly beneath it, in a section holding BOTH
    required-missing and optional-null tasks together (the scenario that
    used to read "5 of 5" over 6 rows)."""
    raw = document_factory.create("SPM", title="probe")
    raw["Parameterisation"]["Cell"]["Volume [m3]"] = None
    d = app_driver
    d.open(_write(tmp_path, "ratio_integrity.json", raw))

    assert d.validation_task_row_count_under_header("Cell — 5 of 5 remaining") == 5


def test_section_with_only_optional_nulls_shows_no_required_header(
    app_driver, tmp_path, valid_spm_dict
):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Header"]["Description"] = None
    d = app_driver
    d.open(_write(tmp_path, "only_optional_header.json", raw))

    headers = d.validation_group_headers()
    assert "Header · optional — 1 unfilled" in headers
    assert not any(h.startswith("Header —") for h in headers)


def test_fold_headers_are_non_activatable(app_driver, tmp_path):
    """The rail redesign (Stage B) replaced the page-level "Issues"/
    "Outstanding" headers with one foldable header per bucket in the
    All-sections view; the same non-activatable contract applies to it --
    a single click folds/unfolds (covered elsewhere), Enter/double-click is
    a structural no-op."""
    d = app_driver
    d.open(_skeleton_path(tmp_path))
    assert d.all_sections_fold_headers()  # premise: at least one bucket renders

    received = []
    d._w._diagnostics.issue_activated.connect(received.append)
    d._w._diagnostics.task_activated.connect(received.append)

    d.activate_fold_header(0)

    assert received == []


def test_group_subheaders_are_non_activatable(app_driver, tmp_path):
    d = app_driver
    d.open(_skeleton_path(tmp_path))
    assert d.validation_group_headers()  # premise: at least one group exists

    received = []
    d._w._diagnostics.issue_activated.connect(received.append)
    d._w._diagnostics.task_activated.connect(received.append)

    d.activate_validation_group_header(0)

    assert received == []
