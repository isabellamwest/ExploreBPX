"""Tests for the rail-redesign bucketing layer (``core.page_buckets``).

Stage A of the rail redesign: pure Python throughout, no Qt.
The point of this module is F3's reconciliation invariant -- every visible
diagnostic and every task lands in exactly ONE rail bucket, so the strip
totals, the rail badges and the All-sections view can never disagree. Every
test below checks that invariant at the identity level (which bucket holds
which exact diagnostic/task object), not just aggregate counts, per the
brief.
"""

from __future__ import annotations

import copy
import json

import pytest

from core import bpx_gateway, completion, document_factory, page_buckets, structure
from core.completion import CompletionTask, PartitionedIssues, TaskKind
from core.document import BPXDocument
from core.page_buckets import DOCUMENT_BUCKET_PATH
from core.validation import PydanticErrorDiagnostic, merge_union_pairs_by_location


def _bucket_page(raw: dict, model: str | None = None):
    """Run the full pipeline (document_completion -> partition_issues ->
    bucket_page_content) exactly as ``main_window._refresh_all`` will, and
    return every intermediate value a test might want to assert against."""
    if model is None:
        model = structure.infer_model(raw)
    doc = BPXDocument.from_raw(raw, filename="probe", fmt="json")
    tasks = completion.document_completion(raw)
    partition = completion.partition_issues(doc, tasks)
    result = page_buckets.bucket_page_content(raw, model, partition, tasks)
    return doc, tasks, partition, result


def _assert_reconciled(tasks: tuple[CompletionTask, ...], partition: PartitionedIssues, result) -> None:
    """F3's own regression test, factored out: totals agree, and every
    visible diagnostic / every task appears in EXACTLY ONE bucket (identity,
    not just count -- ``PydanticErrorDiagnostic`` is a frozen dataclass over
    a dict and is not guaranteed hashable/orderable, so membership is
    checked by object identity via ``id()``, and duplication is checked the
    same way)."""
    merged_visible = merge_union_pairs_by_location(partition.visible)

    assert result.error_count == partition.error_count
    assert result.warning_count == partition.warning_count
    assert result.outstanding_count == len(tasks)

    seen_issue_ids: set[int] = set()
    for bucket in result.buckets:
        for diagnostic, _nav_path in bucket.issues:
            assert id(diagnostic) not in seen_issue_ids, "diagnostic appeared in more than one bucket"
            seen_issue_ids.add(id(diagnostic))
    assert seen_issue_ids == {id(diagnostic) for diagnostic, _ in merged_visible}

    seen_task_ids: set[int] = set()
    for bucket in result.buckets:
        for task in bucket.required_tasks + bucket.optional_tasks:
            assert id(task) not in seen_task_ids, "task appeared in more than one bucket"
            seen_task_ids.add(id(task))
    assert seen_task_ids == {id(task) for task in tasks}


# ---------------------------------------------------------------------------
# Required fixtures (brief): normal invalid file, fresh skeleton, unknown
# top-level section, garbage section value, custom parameters, committed
# nulls, absent required section, Partial, no/garbage model.
# ---------------------------------------------------------------------------


def test_normal_invalid_file_reconciles(valid_spm_dict):
    """Mirrors ``test_validation_page_layout.many_issues_path``: errors spread
    across three sections, one of them a merged float/int union pair
    (decision Q) so the bucket-level count must also reflect the merge, not
    the raw diagnostic count. Deliberately avoids touching ``Header`` here --
    bpx's root dispatcher validates ``Header`` first and an invalid Header
    field suppresses everything else (V4), which is exercised on its own in
    ``test_custom_parameter_extra_forbidden_stays_visible``."""
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "banana"
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = "low"
    raw["Parameterisation"]["Negative electrode"]["Thickness [m]"] = "thin"
    raw["Parameterisation"]["Positive electrode"]["Diffusivity [m2.s-1]"] = "fast"
    _doc, tasks, partition, result = _bucket_page(raw)
    _assert_reconciled(tasks, partition, result)
    assert partition.error_count == 4
    assert result.error_count == 4
    cell_bucket = next(b for b in result.buckets if b.path == ("Parameterisation", "Cell"))
    assert len(cell_bucket.issues) == 2  # two merged union pairs, one row each
    electrode_bucket = next(b for b in result.buckets if b.path == ("Parameterisation", "Positive electrode"))
    assert len(electrode_bucket.issues) == 1  # a custom field, not a union pair


def test_fresh_skeleton_has_zero_issues_and_n_outstanding():
    raw = document_factory.create("SPM", title="probe")
    _doc, tasks, partition, result = _bucket_page(raw, "SPM")
    _assert_reconciled(tasks, partition, result)
    assert result.error_count == 0
    assert result.warning_count == 0
    assert result.outstanding_count == len(tasks) > 0
    assert all(bucket.error_count == 0 for bucket in result.buckets)


def test_unknown_top_level_section_gets_its_own_bucket():
    raw = document_factory.create("SPM", title="probe")
    raw["Electrodes"] = {"Foo": 1}
    _doc, tasks, partition, result = _bucket_page(raw, "SPM")
    _assert_reconciled(tasks, partition, result)
    labels = [bucket.label for bucket in result.buckets]
    assert "Electrodes" in labels
    electrodes = next(b for b in result.buckets if b.path == ("Electrodes",))
    assert electrodes.absent is False


def test_garbage_section_value_stays_visible_in_its_own_bucket():
    """``"Cell": 5`` -- a garbage, non-dict section value. It is present (not
    absent, decision M), draws a real validator type error, and must not be
    absorbed (no task exists for a garbage value, only for a missing one)."""
    raw = document_factory.create("SPM", title="probe")
    raw["Parameterisation"]["Cell"] = 5
    _doc, tasks, partition, result = _bucket_page(raw, "SPM")
    _assert_reconciled(tasks, partition, result)
    cell_bucket = next(b for b in result.buckets if b.path == ("Parameterisation", "Cell"))
    assert cell_bucket.absent is False
    assert cell_bucket.error_count == 1
    assert cell_bucket.required_tasks == ()  # nothing absorbs a garbage value


def test_custom_parameter_extra_forbidden_stays_visible():
    raw = document_factory.create("SPM", title="probe")
    raw["Header"]["NotARealField"] = "x"
    _doc, tasks, partition, result = _bucket_page(raw, "SPM")
    _assert_reconciled(tasks, partition, result)
    header_bucket = next(b for b in result.buckets if b.path == ("Header",))
    assert header_bucket.error_count == 1
    assert not any(t.path == ("Header", "NotARealField") for t in header_bucket.required_tasks)


def test_committed_null_absorbs_into_its_own_bucket(valid_spm_dict):
    raw = json.loads(json.dumps(valid_spm_dict))
    raw["Parameterisation"]["Cell"]["Lower voltage cut-off [V]"] = None
    _doc, tasks, partition, result = _bucket_page(raw)
    _assert_reconciled(tasks, partition, result)
    cell_bucket = next(b for b in result.buckets if b.path == ("Parameterisation", "Cell"))
    assert cell_bucket.error_count == 0  # absorbed, decision E/D
    null_task = next(t for t in cell_bucket.required_tasks if t.kind is TaskKind.NULL_FIELD)
    assert null_task.alias == "Lower voltage cut-off [V]"


def test_absent_required_section_is_one_absent_bucket():
    raw = document_factory.create("SPMe", title="probe")
    del raw["Parameterisation"]["Electrolyte"]
    _doc, tasks, partition, result = _bucket_page(raw, "SPMe")
    _assert_reconciled(tasks, partition, result)
    electrolyte = next(b for b in result.buckets if b.path == ("Parameterisation", "Electrolyte"))
    assert electrolyte.absent is True
    assert electrolyte.required_total is None  # decision M: fields never enumerated
    assert len(electrolyte.required_tasks) == 1
    assert electrolyte.required_tasks[0].kind is TaskKind.MISSING_SECTION


def test_state_absent_from_fresh_scaffold_yields_no_bucket_task_or_diagnostic():
    """bpx 1.1.1 made ``State`` schema-optional (``Field(None, alias="State")``)
    and deleted the root validator that used to demand it for every concrete
    model (obsoleting the old "corrected V1" story this test used to pin):
    a fresh scaffold never has ``State`` at all (``document_factory`` no
    longer adds it), ``document_completion`` raises no task for its absence,
    and the real validator raises no diagnostic either -- so, unlike every
    other schema-required section, there is no ``State`` bucket at all."""
    raw = document_factory.create("SPM", title="probe")
    assert "State" not in raw
    _doc, tasks, partition, result = _bucket_page(raw, "SPM")
    _assert_reconciled(tasks, partition, result)
    assert not any(b.path == ("State",) for b in result.buckets)
    assert not any(t.path == ("State",) for t in tasks)


def test_partial_model_has_no_tasks_and_stripped_locs_land_correctly():
    """The reviewed defect this stage found and fixed: under Partial, the
    validator's own union-branch ``missing`` diagnostics for a sparse
    electrode carry a V4-stripped loc (``('Negative electrode', <field>)``,
    no ``Parameterisation`` prefix, since the field never resolves to an
    existing parameter) -- a naive "first path segment is the bucket" rule
    would create a bogus standalone ``('Negative electrode',)`` bucket
    alongside the real ``('Parameterisation', 'Negative electrode')`` one
    that already exists from the raw walk. Both must land in the SAME bucket.
    """
    raw = document_factory.create("Partial", title="probe")
    raw["Parameterisation"]["Negative electrode"] = {"Thickness [m]": 1e-4}
    _doc, tasks, partition, result = _bucket_page(raw, "Partial")
    _assert_reconciled(tasks, partition, result)
    assert tasks == ()
    electrode_buckets = [b for b in result.buckets if b.label == "Negative electrode"]
    assert len(electrode_buckets) == 1, "must not split into two buckets for the same section"
    assert electrode_buckets[0].path == ("Parameterisation", "Negative electrode")
    assert electrode_buckets[0].error_count == 8  # V3


def test_no_model_yields_declare_model_task_and_stays_visible_error():
    """Decision C: an undeclared model -> exactly one task (declare a model),
    landing under Header. ``partition_issues`` (pre-existing, unmodified by
    this stage) never absorbs into a ``DECLARE_MODEL`` task -- only
    MISSING_SECTION/MISSING_FIELD/NULL_FIELD/the pinned State message do
    (decision E) -- so the validator's own ``missing ('Model',)`` diagnostic
    stays visible alongside the task, both in the Header bucket, same as
    V6's garbage-model case."""
    raw = document_factory.create("SPM", title="probe")
    del raw["Header"]["Model"]
    _doc, tasks, partition, result = _bucket_page(raw, None)
    _assert_reconciled(tasks, partition, result)
    header_bucket = next(b for b in result.buckets if b.path == ("Header",))
    assert len(header_bucket.required_tasks) == 1
    assert header_bucket.required_tasks[0].kind is TaskKind.DECLARE_MODEL
    assert header_bucket.error_count == 1


def test_garbage_model_yields_declare_model_task_and_visible_error():
    raw = document_factory.create("SPM", title="probe")
    raw["Header"]["Model"] = "banana"
    _doc, tasks, partition, result = _bucket_page(raw, None)
    _assert_reconciled(tasks, partition, result)
    header_bucket = next(b for b in result.buckets if b.path == ("Header",))
    assert header_bucket.required_tasks[0].kind is TaskKind.DECLARE_MODEL
    assert header_bucket.error_count == 1  # literal_error, never absorbed (V6)


def test_garbage_model_plus_extra_header_field_both_land_in_header():
    """A second V4-stripped-loc regression: with the model garbage,
    ``document_completion`` short-circuits to the single DECLARE_MODEL task
    (decision C), so a SEPARATE, un-absorbable Header diagnostic has no task
    to absorb into and stays visible -- it must still land in the Header
    bucket, not its own bogus per-field bucket.

    Re-baselined for bpx 1.1.1: this used to pair the garbage Model with a
    missing ``BPX`` field, but bpx 1.1.1 added an ``is_legacy_bpx`` pre-check
    that reads ``Header.BPX`` before pydantic runs at all, so a missing
    ``BPX`` now short-circuits the *whole* document into one raw exception,
    masking the Model diagnostic entirely (probed directly against the real
    validator). A custom, schema-unknown Header field triggers a real,
    still-coexisting ``extra_forbidden`` diagnostic instead.
    """
    raw = document_factory.create("SPM", title="probe")
    raw["Header"]["Model"] = "banana"
    raw["Header"]["Not a real field"] = 1
    _doc, tasks, partition, result = _bucket_page(raw, None)
    _assert_reconciled(tasks, partition, result)
    assert not any(b.label == "Not a real field" for b in result.buckets)
    header_bucket = next(b for b in result.buckets if b.path == ("Header",))
    assert header_bucket.error_count == 2  # literal_error(Model) + extra_forbidden(Not a real field)


# ---------------------------------------------------------------------------
# Document-bucket fallback (F3's third tier)
# ---------------------------------------------------------------------------


def test_entirely_absent_parameterisation_is_a_real_document_bucket_diagnostic():
    """A genuinely un-absorbable, real (not synthetic) document-level
    diagnostic: deleting ``Parameterisation`` entirely raises a
    ``BPXExceptionDiagnostic`` (a raw ``KeyError('Parameterisation')``, not a
    pydantic error -- it has neither ``.error_type`` nor ``.loc`` at all), so
    it never resolves to a parameter, its quoted-token message-recovery
    finds no matching *parameter* (``"Parameterisation"`` names a section,
    not a leaf), and it is not eligible for absorption (``partition_issues``
    only absorbs ``error_type == "missing"``, which this is not). It
    reconciles into the Document bucket alongside the real
    ``MISSING_SECTION ('Parameterisation',)`` task -- itself also routed to
    Document, since a section with no child segment left to promote has
    nothing to be an "ancestor" of but the document root.
    """
    raw = document_factory.create("SPM", title="probe")
    del raw["Parameterisation"]
    _doc, tasks, partition, result = _bucket_page(raw, "SPM")
    _assert_reconciled(tasks, partition, result)
    document_bucket = next(b for b in result.buckets if b.path == DOCUMENT_BUCKET_PATH)
    assert document_bucket.error_count == 1
    assert any(t.path == ("Parameterisation",) for t in document_bucket.required_tasks)


def test_synthetic_unresolvable_diagnostic_falls_back_to_document_bucket():
    """Belt and braces alongside the real case above: feeds
    :func:`page_buckets.bucket_page_content` a hand-built partition carrying
    a synthetic diagnostic with an empty nav_path directly, bypassing
    document attachment entirely, to prove the Document fallback in
    isolation.
    """
    synthetic = PydanticErrorDiagnostic(
        raw_error={"loc": (), "msg": "synthetic unresolvable problem", "type": "value_error"}
    )
    fake_partition = PartitionedIssues(
        visible=((synthetic, ()),),
        absorbed=(),
        absorbed_by_task={},
        error_count=1,
        warning_count=0,
    )
    result = page_buckets.bucket_page_content({"Header": {"Model": "SPM"}}, "SPM", fake_partition, ())
    assert result.buckets[0].path == DOCUMENT_BUCKET_PATH
    assert result.buckets[0].issues == ((synthetic, ()),)
    assert result.error_count == 1


def test_document_bucket_absent_when_unoccupied():
    raw = document_factory.create("SPM", title="probe")
    _doc, tasks, partition, result = _bucket_page(raw, "SPM")
    assert not any(bucket.path == DOCUMENT_BUCKET_PATH for bucket in result.buckets)


def test_document_bucket_first_when_occupied(fixtures_dir):
    """The nmc fixture carries a ``PythonWarningDiagnostic`` (no ``.loc`` at
    all -- nav_path ``()``), which lands in the Document bucket; it must
    render first per F2."""
    raw = json.loads((fixtures_dir / "nmc_pouch_cell_BPX.json").read_text("utf-8"))
    _doc, tasks, partition, result = _bucket_page(raw)
    assert result.buckets[0].path == DOCUMENT_BUCKET_PATH
    assert result.buckets[0].issues  # actually occupied, not a stray empty bucket


# ---------------------------------------------------------------------------
# Ordering and bucket-flag checks
# ---------------------------------------------------------------------------


def test_buckets_are_in_document_order_with_absent_section_at_its_schema_position():
    """``Parameterisation``'s children walk in the schema's own declaration
    order (Cell, Electrolyte, Negative electrode, Positive electrode,
    Separator -- ``structure.required_sections``, which now derives it live),
    not ``raw``'s own key order, so a schema-required-but-absent child (a
    deleted SPMe ``Electrolyte``) still gets its natural position instead of
    being stranded wherever ``document_completion``'s task walk happens to
    first name it. (``State`` is schema-optional since bpx 1.1.1 and is
    never scaffolded, so it is not one of the buckets here.)"""
    raw = document_factory.create("SPMe", title="probe")
    del raw["Parameterisation"]["Electrolyte"]
    _doc, tasks, partition, result = _bucket_page(raw, "SPMe")
    labels = [bucket.label for bucket in result.buckets]
    assert labels == ["Header", "Cell", "Electrolyte", "Negative electrode", "Positive electrode", "Separator"]


def test_required_total_is_none_for_absent_sections_and_the_document_bucket():
    raw = document_factory.create("SPM", title="probe")
    del raw["Header"]
    _doc, tasks, partition, result = _bucket_page(raw, None)
    header_bucket = next(b for b in result.buckets if b.path == ("Header",))
    assert header_bucket.absent is True
    assert header_bucket.required_total is None


# ---------------------------------------------------------------------------
# The keystone case from core.completion's own test suite, re-verified at
# the bucket level: a suppressed validator diagnostic (Cell's mode="before"
# validator hides its own missing-field check) is invisible to bpx but still
# surfaces as an Outstanding task, correctly bucketed under Cell.
# ---------------------------------------------------------------------------


def test_keystone_nmc_cell_field_deletion_still_reconciles(valid_spm_dict):
    """Depends on the same premise as
    ``test_completion.test_keystone_cell_field_deletion_invisible_to_validator``:
    a document that already trips ``Cell``'s ``mode="before"`` validator at
    baseline leaves the validator's own diagnostics unchanged when a required
    Cell field is also deleted, while completion still reports the task.

    Re-baselined for bpx 1.1.1: the nmc fixture this used to read is a legacy
    BPX v0.x object (``Header.BPX`` < 1), and bpx 1.1.1 auto-converts those
    cleanly (probed directly -- it now validates with warnings only, no
    ``value_error``), so it no longer trips the premise. A deprecated field
    is injected directly into a genuinely-v1 document instead (``Header.BPX``
    >= 1, so bpx does not treat it as legacy) -- the injected field is what
    trips ``Cell``'s validator, not legacy conversion.
    """
    raw = copy.deepcopy(valid_spm_dict)
    raw["Parameterisation"]["Cell"]["Ambient temperature [K]"] = 298.15
    baseline_issues = bpx_gateway.validate(raw).issues
    assert any(
        getattr(d, "error_type", None) == "value_error" and getattr(d, "loc", None) == ("Cell",)
        for d in baseline_issues
    ), "premise: the injected deprecated field must trip Cell's mode='before' validator"

    del raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]
    _doc, tasks, partition, result = _bucket_page(raw)
    _assert_reconciled(tasks, partition, result)

    cell_bucket = next(b for b in result.buckets if b.path == ("Parameterisation", "Cell"))
    assert any(
        t.kind is TaskKind.MISSING_FIELD and t.alias == "Nominal cell capacity [A.h]"
        for t in cell_bucket.required_tasks
    )


# ---------------------------------------------------------------------------
# All real fixtures, as a blanket reconciliation sweep.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_name",
    [
        "nmc_pouch_cell_BPX.json",
        "lfp_18650_cell_BPX.json",
        "invalid_blended_state_mismatch.json",
        "warning_legacy_bpx_float.json",
        "spm_example_valid.json",
    ],
)
def test_real_fixtures_reconcile(fixtures_dir, fixture_name):
    raw = json.loads((fixtures_dir / fixture_name).read_text("utf-8"))
    _doc, tasks, partition, result = _bucket_page(raw)
    _assert_reconciled(tasks, partition, result)
