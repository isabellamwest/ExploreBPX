"""Tests for the pure completion query (``core.completion``).

Pure Python throughout -- no Qt. These tests hold implementation to the
verified facts and locked decisions.
"""

from __future__ import annotations

import copy
import json

import pytest

from core import bpx_gateway, completion, document_factory, validation
from core.completion import CompletionTask, TaskKind
from core.document import BPXDocument


def _diagnostic_tuples(issues):
    return [(getattr(d, "error_type", None), getattr(d, "loc", None), d.message) for d in issues]


def test_keystone_cell_field_deletion_invisible_to_validator(valid_spm_dict):
    """Deleting a required Cell field from a document whose Cell already
    trips a ``mode="before"`` validator leaves the validator's own issue list
    unchanged, while completion reports it.

    This is the fact the whole layer exists to fix: ``Cell`` has a
    ``mode="before"`` validator (a deprecated-fields check) that raises
    before pydantic ever checks Cell's own required fields.

    Re-baselined for bpx 1.1.1: this used to read the nmc fixture, which
    tripped the check via its own pre-existing deprecated
    ``'Initial temperature [K]'``/``'Ambient temperature [K]'`` fields --
    but that fixture is a legacy BPX v0.x object (``Header.BPX`` < 1), and
    bpx 1.1.1 auto-converts those cleanly (probed directly against the real
    validator: it now validates with warnings only), so it no longer trips
    this premise. A deprecated field is injected directly into a genuinely-v1
    document instead (``Header.BPX`` >= 1, so bpx does not treat it as
    legacy) -- the injected field is what trips the validator, not legacy
    conversion.
    """
    raw = copy.deepcopy(valid_spm_dict)
    raw["Parameterisation"]["Cell"]["Ambient temperature [K]"] = 298.15
    baseline_issues = bpx_gateway.validate(raw).issues
    assert any(
        getattr(d, "error_type", None) == "value_error" and getattr(d, "loc", None) == ("Cell",)
        for d in baseline_issues
    ), "premise: the injected deprecated field must trip Cell's mode='before' validator"

    baseline_tasks = completion.document_completion(raw)

    mutated = copy.deepcopy(raw)
    del mutated["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]
    mutated_issues = bpx_gateway.validate(mutated).issues

    assert _diagnostic_tuples(mutated_issues) == _diagnostic_tuples(baseline_issues)

    mutated_tasks = completion.document_completion(mutated)
    new_tasks = set(mutated_tasks) - set(baseline_tasks)
    assert new_tasks == {
        CompletionTask(
            TaskKind.MISSING_FIELD,
            ("Parameterisation", "Cell", "Nominal cell capacity [A.h]"),
            "Nominal cell capacity [A.h]",
            True,
        )
    }


def test_partial_sparse_electrode_has_no_tasks_but_suggests_fields():
    raw = document_factory.create("Partial", title="probe")
    raw["Parameterisation"]["Negative electrode"] = {"Thickness [m]": 1e-4}

    assert completion.document_completion(raw) == ()

    section = completion.completion_for(
        ("Parameterisation", "Negative electrode"),
        raw["Parameterisation"]["Negative electrode"],
        "Partial",
    )
    assert section.missing_fields
    assert all(field.required is False for field in section.missing_fields)
    assert section.null_fields == ()


def test_null_required_field_is_outstanding_not_missing():
    raw = document_factory.create("SPM", title="probe")
    cell = raw["Parameterisation"]["Cell"]
    cell["Electrode area [m2]"] = 1.0
    cell["Number of electrode pairs connected in parallel to make a cell"] = 1
    cell["Lower voltage cut-off [V]"] = 2.5
    cell["Upper voltage cut-off [V]"] = 4.2
    cell["Nominal cell capacity [A.h]"] = None

    tasks = completion.document_completion(raw)
    null_task = CompletionTask(
        TaskKind.NULL_FIELD,
        ("Parameterisation", "Cell", "Nominal cell capacity [A.h]"),
        "Nominal cell capacity [A.h]",
        True,
    )
    assert null_task in tasks
    missing_task = CompletionTask(
        TaskKind.MISSING_FIELD,
        ("Parameterisation", "Cell", "Nominal cell capacity [A.h]"),
        "Nominal cell capacity [A.h]",
        True,
    )
    assert missing_task not in tasks


def test_empty_list_is_a_committed_value_not_outstanding():
    """A ``[]`` is a real, if invalid, value -- the outstanding/null rule
    is restricted to literal ``None`` only."""
    raw = document_factory.create("SPM", title="probe")
    cell = raw["Parameterisation"]["Cell"]
    cell["Electrode area [m2]"] = 1.0
    cell["Number of electrode pairs connected in parallel to make a cell"] = 1
    cell["Lower voltage cut-off [V]"] = 2.5
    cell["Upper voltage cut-off [V]"] = 4.2
    cell["Nominal cell capacity [A.h]"] = []

    tasks = completion.document_completion(raw)
    capacity_path = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    assert not any(task.path == capacity_path for task in tasks)


def test_garbage_model_yields_only_declare_model_task():
    raw = document_factory.create("SPM", title="probe")
    raw["Header"]["Model"] = "banana"
    assert completion.document_completion(raw) == (
        CompletionTask(TaskKind.DECLARE_MODEL, ("Header", "Model"), "Model", True),
    )


def test_undeclared_model_yields_only_declare_model_task():
    raw = document_factory.create("SPM", title="probe")
    del raw["Header"]["Model"]
    assert completion.document_completion(raw) == (
        CompletionTask(TaskKind.DECLARE_MODEL, ("Header", "Model"), "Model", True),
    )


def test_absent_header_yields_only_missing_header_task():
    raw = document_factory.create("SPM", title="probe")
    del raw["Header"]
    assert completion.document_completion(raw) == (
        CompletionTask(TaskKind.MISSING_SECTION, ("Header",), None, True),
    )


def test_absent_required_section_then_cascade_on_readd():
    """Deleting Electrolyte (SPMe/DFN) collapses to one section-absent task
    with no field enumeration; re-adding it empty immediately enumerates its
    fields via the cascade -- free from per-section recompute, no extra code."""
    raw = document_factory.create("SPMe", title="probe")
    del raw["Parameterisation"]["Electrolyte"]

    tasks = completion.document_completion(raw)
    electrolyte_path = ("Parameterisation", "Electrolyte")
    section_tasks = [t for t in tasks if t.path == electrolyte_path]
    assert section_tasks == [CompletionTask(TaskKind.MISSING_SECTION, electrolyte_path, None, True)]
    field_tasks = [t for t in tasks if t.path[:2] == electrolyte_path and len(t.path) > 2]
    assert field_tasks == []

    raw["Parameterisation"]["Electrolyte"] = {}
    tasks_after = completion.document_completion(raw)
    assert not any(t.path == electrolyte_path and t.kind is TaskKind.MISSING_SECTION for t in tasks_after)
    field_tasks_after = [t for t in tasks_after if t.path[:2] == electrolyte_path and len(t.path) > 2]
    assert field_tasks_after  # cascade: fields enumerate immediately


# --- bpx 1.1.1: State (and its own children) are schema-optional ---------
#
# bpx 1.1.0 had a root `mode="after"` validator that demanded State for every
# concrete model ("'State' section must be provided unless using a 'Partial'
# parameterisation"); bpx 1.1.1 deleted that validator and made `State` a
# genuinely optional field (`Field(None, alias="State")`), so a valid
# concrete document with State removed now validates cleanly. These tests
# pin that against the real validator (not a restated/assumed message).


def test_valid_spm_minus_state_yields_no_task_and_no_diagnostics(valid_spm_dict):
    """Removing State from an otherwise-valid document is now a no-op for
    both completion and validation: no task, no diagnostic."""
    raw = copy.deepcopy(valid_spm_dict)
    del raw["State"]

    tasks = completion.document_completion(raw)
    assert not any(t.path == ("State",) for t in tasks)
    assert bpx_gateway.validate(raw).issues == []

    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    result = completion.partition_issues(doc, tasks)
    assert result.visible == ()
    assert result.absorbed == ()
    assert result.error_count == 0


def test_state_optional_is_pinned_against_the_real_validator(valid_spm_dict):
    """Loud-failure pin of the bpx 1.1.1 contract, read from the real
    validator: a valid concrete document with State removed draws ZERO
    diagnostics. If a future bpx release reintroduces a State-required
    check, THIS test must fail loudly -- ``document_completion`` would then
    need its own ``MISSING_SECTION ("State",)`` special case reinstated
    (see git history for the pre-1.1.1 implementation) rather than letting
    the root diagnostic reappear as an unexplained, unabsorbed Issue.
    """
    raw = copy.deepcopy(valid_spm_dict)
    del raw["State"]
    assert bpx_gateway.validate(raw).issues == []


def test_empty_state_on_clean_document_yields_no_tasks_or_diagnostics(valid_spm_dict):
    """State's own children (Initial conditions/Thermal environment/
    Degradation) are all schema-optional too (bpx 1.1.1), so committing an
    empty ``State: {}`` on an otherwise-valid document adds no completion
    task and draws no validator diagnostic -- there is nothing here for
    completion to absorb."""
    raw = copy.deepcopy(valid_spm_dict)
    raw["State"] = {}

    tasks = completion.document_completion(raw)
    assert not any(t.path[:1] == ("State",) for t in tasks)
    assert bpx_gateway.validate(raw).issues == []

    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    result = completion.partition_issues(doc, tasks)
    assert result.visible == ()
    assert result.absorbed == ()


def test_partial_has_no_state_task():
    raw = document_factory.create("Partial", title="probe")
    assert completion.document_completion(raw) == ()


# --- Asymmetric loc-prefix matching ---------------------------------------


def test_header_field_absorption_regression(valid_spm_dict):
    """A missing ``Header.BPX`` diagnostic used to carry nav_path
    ``('BPX',)`` -- the validator dropping a leading ``Header`` component,
    exactly like it drops ``Parameterisation`` -- and a matcher that only
    stripped ``Parameterisation`` left every required Header field
    double-surfaced.

    bpx 1.1.1 added an ``is_legacy_bpx`` pre-check that reads ``Header.BPX``
    *before* pydantic validation runs at all, so a document missing it no
    longer raises the plain pydantic ``missing`` error the old fix absorbed
    -- it raises a bare ``ValueError`` instead, wrapped as a
    :class:`core.validation.BPXExceptionDiagnostic` with neither
    ``error_type`` nor ``loc``. ``document_completion`` still reports the
    schema-required ``MISSING_FIELD`` task (it never reads diagnostics), but
    ``partition_issues`` cannot match a diagnostic carrying no
    ``error_type``/``loc`` to it, so -- faithfully surfacing bpx's new
    behaviour, not a bug -- the task and the real validator's own message now
    stay visible side by side (mirrors the ``DECLARE_MODEL`` case).
    """
    raw = copy.deepcopy(valid_spm_dict)
    del raw["Header"]["BPX"]

    tasks = completion.document_completion(raw)
    assert CompletionTask(TaskKind.MISSING_FIELD, ("Header", "BPX"), "BPX", True) in tasks

    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    result = completion.partition_issues(doc, tasks)
    assert result.absorbed == ()
    assert len(result.visible) == 1
    diagnostic, _nav_path = result.visible[0]
    assert getattr(diagnostic, "error_type", None) is None
    assert "BPX" in diagnostic.message


def test_validation_run_field_absorption_keeps_full_prefix(valid_spm_dict):
    """A Validation run's own required fields (``Time``/``Current``/
    ``Voltage`` -- NOT ``Temperature``, which is optional in ``Experiment``)
    absorb via nav_path ``('Validation', <run>, <field>)`` unchanged: unlike
    Header/Parameterisation, the validator KEEPS the ``Validation`` prefix in
    full. This exercises the "no prefix to strip" branch of
    ``_nav_path_candidates``, not just the two stripped ones.
    """
    raw = copy.deepcopy(valid_spm_dict)
    raw["Validation"] = {
        "C/20": {
            "Current [A]": [-0.5, -0.5],
            "Voltage [V]": [4.2, 4.0],
            "Temperature [K]": [298.15, 298.15],
        }
    }

    tasks = completion.document_completion(raw)
    time_path = ("Validation", "C/20", "Time [s]")
    assert CompletionTask(TaskKind.MISSING_FIELD, time_path, "Time [s]", True) in tasks
    # Temperature is optional in Experiment -- must never become a task.
    assert not any(t.path == ("Validation", "C/20", "Temperature [K]") for t in tasks)

    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    result = completion.partition_issues(doc, tasks)
    absorbed_locs = {nav for _, nav in result.absorbed}
    assert ("Validation", "C/20", "Time [s]") in absorbed_locs


def test_partition_handles_warning_diagnostics_without_crashing(fixtures_dir):
    """The nmc fixture carries a ``PythonWarningDiagnostic`` (no
    ``error_type``/``loc`` attributes at all) alongside its two ``value_error``
    diagnostics. ``partition_issues`` must not crash on it (the
    ``getattr``-defensive path was previously untested); the warning stays
    visible (nothing absorbs a diagnostic with no ``error_type``/``loc``) and
    is counted in ``warning_count``.
    """
    raw = json.loads((fixtures_dir / "nmc_pouch_cell_BPX.json").read_text("utf-8"))
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    tasks = completion.document_completion(raw)

    result = completion.partition_issues(doc, tasks)  # must not raise

    warning_diagnostics = [d for d, _ in result.visible if getattr(d, "error_type", None) is None]
    assert warning_diagnostics
    assert result.warning_count == len(warning_diagnostics)
    assert result.warning_count >= 1


# --- document_completion is Required-only ---------------------------------


def test_document_completion_missing_field_excludes_optional_fields():
    """An *absent* Expected-but-optional field is never a MISSING_FIELD
    task -- those are suggestions only, reachable through ``completion_for``.
    NULL_FIELD has its own rule -- see
    ``test_optional_null_field_is_outstanding_without_required_tag`` below;
    MISSING_FIELD stays Required-only, unaffected."""
    raw = document_factory.create("SPM", title="probe")
    tasks = completion.document_completion(raw)
    assert all(task.required for task in tasks if task.kind is TaskKind.MISSING_FIELD)
    assert not any(task.path == ("Header", "Description") for task in tasks)
    assert not any(task.path == ("Header", "References") for task in tasks)


def test_optional_null_field_is_outstanding_without_required_tag():
    """Any schema-Expected field committed null is Outstanding, Required or
    not. Header's ``Description`` is schema-Expected but NOT schema-required
    -- committing it null must still produce a NULL_FIELD task, with
    ``required=False`` so the Outstanding row renders without the REQUIRED
    tag."""
    raw = document_factory.create("SPM", title="probe")
    raw["Header"]["Description"] = None
    tasks = completion.document_completion(raw)
    null_task = next((t for t in tasks if t.path == ("Header", "Description")), None)
    assert null_task is not None
    assert null_task.kind is TaskKind.NULL_FIELD
    assert null_task.required is False


def test_optional_null_field_absorbs_its_diagnostic_calm_page():
    """The real validator does raise for a committed-null optional string
    field (``Description`` is not schema-nullable, so ``None`` there is a
    real ``string_type`` error) -- creating an expected field never makes the
    document look worse, so this absorbs into the NULL_FIELD task exactly
    like a Required null field does."""
    raw = document_factory.create("SPM", title="probe")
    raw["Header"]["Description"] = None
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    tasks = completion.document_completion(raw)
    null_task = next(t for t in tasks if t.path == ("Header", "Description"))

    result = completion.partition_issues(doc, tasks)

    assert any(
        getattr(d, "error_type", None) == "string_type" and nav == ("Header", "Description")
        for d, nav in result.absorbed
    )
    assert not any(nav == ("Description",) for _, nav in result.visible)
    assert result.absorbed_by_task.get(null_task)
    assert result.absorbed_by_task[null_task][0][0].message == "Input should be a valid string"


def test_custom_null_parameter_gets_no_task_and_stays_visible():
    """A custom parameter's ``extra_forbidden`` rejects the *name*, not the
    emptiness -- filling a value fixes nothing, so it must never absorb,
    unlike an expected field's null."""
    raw = document_factory.create("SPM", title="probe")
    raw["Header"]["NotARealField"] = None
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")

    tasks = completion.document_completion(raw)
    assert not any(t.path == ("Header", "NotARealField") for t in tasks)

    result = completion.partition_issues(doc, tasks)
    assert any(
        getattr(d, "error_type", None) == "extra_forbidden" and nav == ("Header", "NotARealField")
        for d, nav in result.visible
    )


def test_partition_calm_badge_spm_skeleton_absorbs_everything():
    raw = document_factory.create("SPM", title="probe")
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    tasks = completion.document_completion(raw)

    result = completion.partition_issues(doc, tasks)

    assert result.visible == ()
    assert result.error_count == 0
    assert result.warning_count == 0
    assert result.absorbed  # something real was absorbed, not a vacuous pass
    assert len(result.absorbed) == len(doc.issues)


def test_partition_partial_sparse_electrode_stays_fully_visible():
    """Under Partial no tasks exist, so the validator's own union-branch
    ``missing`` errors are never absorbed."""
    raw = document_factory.create("Partial", title="probe")
    raw["Parameterisation"]["Negative electrode"] = {"Thickness [m]": 1e-4}
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    tasks = completion.document_completion(raw)
    assert tasks == ()

    result = completion.partition_issues(doc, tasks)

    assert len(result.visible) == 8
    assert result.absorbed == ()
    assert all(getattr(d, "error_type", None) == "missing" for d, _ in result.visible)
    assert result.error_count == 8


def test_partial_null_field_becomes_task_and_absorbs(valid_spm_dict):
    """Partial carries NULL_FIELD tasks -- an empty field is outstanding, not
    a red error, exactly as under a concrete model: a complete document
    flipped to Partial with one field emptied must not show that field as a
    page-visible red error."""
    raw = copy.deepcopy(valid_spm_dict)
    raw["Header"]["Model"] = "Partial"
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = None

    tasks = completion.document_completion(raw)
    assert tasks == (
        CompletionTask(
            TaskKind.NULL_FIELD,
            ("Parameterisation", "Cell", "Nominal cell capacity [A.h]"),
            "Nominal cell capacity [A.h]",
            False,  # nothing is Required under Partial
        ),
    )

    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    result = completion.partition_issues(doc, tasks)
    assert result.visible == ()
    assert result.error_count == 0
    assert result.absorbed  # both union-branch nulls re-seated, not silenced


def test_partial_null_and_missing_split_cleanly(valid_spm_dict):
    """In one Partial document, a committed null absorbs into its NULL_FIELD
    task while a sparse electrode's own union-branch ``missing`` errors stay
    fully visible."""
    raw = copy.deepcopy(valid_spm_dict)
    raw["Header"]["Model"] = "Partial"
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = None
    raw["Parameterisation"]["Negative electrode"] = {"Thickness [m]": 1e-4}

    tasks = completion.document_completion(raw)
    assert [t.kind for t in tasks] == [TaskKind.NULL_FIELD]

    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    result = completion.partition_issues(doc, tasks)
    assert result.visible  # the sparse electrode's own errors, untouched
    assert all(getattr(d, "error_type", None) == "missing" for d, _ in result.visible)
    assert all(nav[-2] == "Negative electrode" for _, nav in result.visible)
    assert result.absorbed  # the null's union pair


def _section_paths(raw):
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    tasks = completion.document_completion(raw)
    partition = completion.partition_issues(doc, tasks)
    return completion.visible_error_section_paths(doc, partition)


def test_visible_error_section_paths_calm_for_merely_empty_document():
    """A document whose only 'errors' are unfilled fields -- required fields
    absent (a fresh scaffold) plus one committed null -- must mark NO
    section. Emptiness is outstanding work everywhere else (list rows,
    badge); the tree dot must agree."""
    raw = document_factory.create("SPM", title="probe")
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = None

    assert _section_paths(raw) == frozenset()


def test_visible_error_section_paths_marks_bad_value_section_only(valid_spm_dict):
    """A genuinely wrong value stays a red dot -- on its own section, not on
    ancestors (the collapsed-rollup prefix match is the Qt model's job)."""
    raw = copy.deepcopy(valid_spm_dict)
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = []

    assert _section_paths(raw) == frozenset({("Parameterisation", "Cell")})


def test_visible_error_section_paths_marks_extra_forbidden_custom(valid_spm_dict):
    """The custom rule carries over to the tree: an ``extra_forbidden``
    custom parameter is name-rejection, never absorbed, so its section keeps
    the dot."""
    raw = copy.deepcopy(valid_spm_dict)
    raw["Parameterisation"]["Cell"]["My bespoke thing"] = 3.0

    assert ("Parameterisation", "Cell") in _section_paths(raw)


def test_visible_error_section_paths_partial_sparse_electrode_still_marked(valid_spm_dict):
    """Under Partial a *present but sparse* section's union-branch
    ``missing`` errors stay visible, so its dot stays -- while a
    committed-null field elsewhere marks nothing."""
    raw = copy.deepcopy(valid_spm_dict)
    raw["Header"]["Model"] = "Partial"
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = None
    raw["Parameterisation"]["Negative electrode"] = {"Thickness [m]": 1e-4}

    paths = _section_paths(raw)
    assert ("Parameterisation", "Negative electrode") in paths
    assert ("Parameterisation", "Cell") not in paths


def test_partition_null_field_absorbs_both_union_branch_diagnostics():
    """A committed-null ``FloatInt`` field raises two diagnostics (one per
    union branch); both must absorb, not just one."""
    raw = document_factory.create("SPM", title="probe")
    cell = raw["Parameterisation"]["Cell"]
    cell["Electrode area [m2]"] = 1.0
    cell["Number of electrode pairs connected in parallel to make a cell"] = 1
    cell["Lower voltage cut-off [V]"] = 2.5
    cell["Upper voltage cut-off [V]"] = 4.2
    cell["Nominal cell capacity [A.h]"] = None
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    tasks = completion.document_completion(raw)

    result = completion.partition_issues(doc, tasks)

    capacity_diagnostics = [
        (d, nav)
        for d, nav in doc.iter_issues()
        if nav == ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    ]
    assert len(capacity_diagnostics) == 2  # float_type + int_type
    # PydanticErrorDiagnostic wraps a raw error dict, so it is unhashable --
    # compare by list membership (uses __eq__), not a set.
    assert all(pair in result.absorbed for pair in capacity_diagnostics)
    assert not any(pair in result.visible for pair in capacity_diagnostics)


def test_partition_null_function_table_field_absorbs_all_four_branches():
    """A committed-null function/table union field raises FOUR diagnostics
    -- ``float_type``/``int_type``/``string_type``/``model_type``, one per
    union branch -- and pydantic tags the function/table branches with names
    (``function-after[validate(), str]``, ``InterpolatedTable``) that the
    old ``_NAV_STRIP_TAGS`` denylist never matched, so those nav_paths kept
    a bogus trailing component and absorption missed them: the field
    rendered grey AND red at once. The fix stores the resolved parameter's
    canonical ``.path`` as nav_path, so all four absorb into the one
    NULL_FIELD task; the display merge then shows exactly three messages
    (float+int collapse, string and table stay distinct)."""
    raw = document_factory.create("SPM", title="probe")
    path = ("Parameterisation", "Negative electrode", "Diffusivity [m2.s-1]")
    raw["Parameterisation"]["Negative electrode"]["Diffusivity [m2.s-1]"] = None
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    tasks = completion.document_completion(raw)
    null_task = next(t for t in tasks if t.path == path)
    assert null_task.kind is TaskKind.NULL_FIELD

    result = completion.partition_issues(doc, tasks)

    absorbed_here = result.absorbed_by_task[null_task]
    assert {getattr(d, "error_type", None) for d, _ in absorbed_here} == {
        "float_type",
        "int_type",
        "string_type",
        "model_type",
    }
    assert all(nav == path for _, nav in absorbed_here)
    assert result.visible == ()
    assert result.error_count == 0
    merged = validation.merge_union_pair(tuple(d for d, _ in absorbed_here))
    assert [d.message for d in merged] == [
        "Input should be a valid number",
        "Input should be a valid string",
        "Input should be a valid dictionary or instance of InterpolatedTable",
    ]


def _set_leaf(raw, path, value):
    node = raw
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


@pytest.mark.parametrize("model", ["SPM", "SPMe", "DFN"])
def test_every_expected_field_committed_null_absorbs_fully(model):
    """Class-of-bug regression for the diffusivity fix: scaffold every
    section the completion cascade enumerates, commit every expected field
    ``null``, and assert the whole document stays calm -- every diagnostic
    (whatever union branch or pydantic tag produced it) absorbs into its
    NULL_FIELD task, and every absorbed nav_path equals the task's canonical
    parameter path. A future bpx branch-tag rename cannot silently reopen
    the bug without failing here."""
    raw = document_factory.create(model, title="probe")
    for _ in range(6):
        tasks = completion.document_completion(raw)
        pending = [
            t for t in tasks if t.kind in (TaskKind.MISSING_SECTION, TaskKind.MISSING_FIELD)
        ]
        if not pending:
            break
        for task in pending:
            _set_leaf(raw, task.path, {} if task.kind is TaskKind.MISSING_SECTION else None)
    tasks = completion.document_completion(raw)
    assert tasks and all(t.kind is TaskKind.NULL_FIELD for t in tasks)

    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    result = completion.partition_issues(doc, tasks)

    assert result.visible == ()
    assert result.error_count == 0
    assert result.warning_count == 0
    assert len(result.absorbed) == len(doc.issues)
    for task, pairs in result.absorbed_by_task.items():
        assert all(nav == task.path for _, nav in pairs)


def test_partition_garbage_model_shows_both_error_and_task():
    """A garbage Model value stays a visible Issue (literal_error, a
    user-typed bad value, never absorbed) *and* the declare-model task is
    still reported -- both are shown, deliberately."""
    raw = document_factory.create("SPM", title="probe")
    raw["Header"]["Model"] = "banana"
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    tasks = completion.document_completion(raw)

    assert tasks == (CompletionTask(TaskKind.DECLARE_MODEL, ("Header", "Model"), "Model", True),)

    result = completion.partition_issues(doc, tasks)
    assert any(
        getattr(d, "error_type", None) == "literal_error" and nav == ("Header", "Model")
        for d, nav in result.visible
    )


def test_container_field_never_becomes_a_missing_field_suggestion():
    """A blended electrode's ``Particle`` container must never show up as a
    missing-field suggestion (the add-parameter popup learned this the hard
    way -- a container "field" is not addable as a parameter)."""
    value = {"Particle": {"Primary": {}}}
    section = completion.completion_for(("Parameterisation", "Negative electrode"), value, "DFN")
    assert all(field.alias != "Particle" for field in section.missing_fields)
    assert all(field.alias != "Particle" for field in section.null_fields)


# --- required_total (the Outstanding page's "M") ---------------------------


def test_required_total_counts_schema_required_non_container_fields():
    """Cell declares 5 schema-required leaf fields (Electrode area, electrode
    pairs, both voltage cut-offs, Nominal cell capacity) -- containers never
    count (there are none on Cell), and this must match regardless of which
    of those fields are actually present."""
    raw = document_factory.create("SPM", title="probe")
    section = completion.completion_for(
        ("Parameterisation", "Cell"), raw["Parameterisation"]["Cell"], "SPM"
    )
    assert section.required_total == 5


def test_required_total_is_not_gated_by_model_concreteness():
    """Unlike ``MissingField.required``, ``required_total`` is a pure schema
    fact: Header's ``BPX``/``Model`` stay required-total==2 even with no
    model declared at all -- otherwise the DECLARE_MODEL task's own
    Outstanding group header would read "1 of 0 remaining"."""
    raw = document_factory.create("SPM", title="probe")
    section = completion.completion_for(("Header",), raw["Header"], None)
    assert section.required_total == 2


def test_ordering_is_deterministic_and_document_ordered():
    raw = document_factory.create("SPMe", title="probe")
    first = completion.document_completion(raw)
    second = completion.document_completion(copy.deepcopy(raw))
    assert first == second

    # Header's own fields are all optional (filtered out of
    # document_completion entirely -- see the required-only regression test
    # below), so Cell's required fields are the earliest document-ordered
    # tasks, followed by each Parameterisation child in the schema's own
    # declaration order (the scaffold inserts keys in
    # ``structure.required_sections`` order, which derives it live:
    # Cell, Electrolyte, Negative electrode, Positive electrode, Separator).
    # ``State`` is no longer scaffolded (bpx 1.1.1: schema-optional, so the
    # factory never adds it).
    cell_positions = [i for i, t in enumerate(first) if t.path[:2] == ("Parameterisation", "Cell")]
    electrolyte_positions = [
        i for i, t in enumerate(first) if t.path[:2] == ("Parameterisation", "Electrolyte")
    ]
    electrode_positions = [
        i for i, t in enumerate(first) if t.path[:2] == ("Parameterisation", "Negative electrode")
    ]
    assert cell_positions and electrolyte_positions and electrode_positions
    assert max(cell_positions) < min(electrolyte_positions)
    assert max(electrolyte_positions) < min(electrode_positions)
