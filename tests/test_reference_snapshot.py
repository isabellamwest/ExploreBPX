"""ReferenceSnapshot: a frozen, read-only reference file load round-trip."""

from __future__ import annotations

import json

from core import bpx_gateway, completion
from core.document import BPXDocument
from state.reference_snapshot import ReferenceSnapshot


def test_load_round_trip_from_a_real_bundled_example(nmc_pouch_cell_path):
    """Model, counts and validity summary match the file's own contents; the
    raw dict matches ``bpx_gateway.load_raw`` verbatim, and mtime is
    populated (captured for a later milestone)."""
    snapshot = ReferenceSnapshot.load(nmc_pouch_cell_path)

    assert snapshot.path == nmc_pouch_cell_path
    assert snapshot.filename == nmc_pouch_cell_path.name
    assert snapshot.model == "DFN"
    # A genuine About:Energy file: valid overall, but with 3 warning-severity
    # diagnostics -- a real, non-fixture-authored "not totally clean" case.
    assert snapshot.error_count == 0
    assert snapshot.warning_count == 3
    assert snapshot.section_count == 16
    assert snapshot.parameter_count == 74
    assert snapshot.mtime > 0

    expected_raw, _fmt = bpx_gateway.load_raw(
        nmc_pouch_cell_path.read_bytes(), nmc_pouch_cell_path.name
    )
    assert snapshot.raw == expected_raw


def test_load_reports_no_model_as_none(tmp_path):
    """A document with no declared Header.Model normalises to None, not ""."""
    path = tmp_path / "no_model.json"
    path.write_text('{"Header": {}}', encoding="utf-8")

    snapshot = ReferenceSnapshot.load(path)

    assert snapshot.model is None


def test_load_reports_errors_for_an_invalid_file(nmc_pouch_cell_path, tmp_path):
    """Breaking a copy of a real bundled file surfaces a real validator error,
    never an invented one -- and the count matches the same
    ``core.completion`` derivation the main document path uses, not the raw
    pre-absorption ``BPXDocument.error_count`` (an undeclared Model is a
    ``DECLARE_MODEL`` task, which ``partition_issues`` never absorbs, so the
    diagnostic stays a real, visible error either way)."""
    raw = json.loads(nmc_pouch_cell_path.read_text("utf-8"))
    del raw["Header"]["Model"]
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(raw), encoding="utf-8")

    snapshot = ReferenceSnapshot.load(broken)

    document = BPXDocument.from_raw(raw, filename="broken.json", fmt="json")
    expected_errors, expected_warnings = completion.partitioned_counts(document)
    assert expected_errors >= 1
    assert snapshot.error_count == expected_errors
    assert snapshot.warning_count == expected_warnings


def test_reference_and_main_document_agree_on_a_missing_required_field(
    valid_spm_path, tmp_path
):
    """The defect this guards: a required field deleted from a file used to
    read as an "error" when the file was pinned as a reference (raw,
    pre-absorption ``BPXDocument.error_count``) while the very same file, as
    the main document, absorbed it into an Outstanding task and showed zero
    errors. A reference must reach the same verdict as a main document."""
    raw = json.loads(valid_spm_path.read_text("utf-8"))
    del raw["Parameterisation"]["Cell"]["Electrode area [m2]"]
    broken = tmp_path / "missing_required_field.json"
    broken.write_text(json.dumps(raw), encoding="utf-8")

    snapshot = ReferenceSnapshot.load(broken)

    document = BPXDocument.from_raw(raw, filename="missing_required_field.json", fmt="json")
    tasks = completion.document_completion(raw)
    partition = completion.partition_issues(document, tasks)
    # The missing field is absorbed into an Outstanding task, not a visible
    # error -- proven against the raw, pre-absorption count too, so this
    # test would have failed against the old implementation.
    assert document.error_count == 1
    assert partition.error_count == 0
    assert snapshot.error_count == partition.error_count == 0
    assert snapshot.warning_count == partition.warning_count == 0


def test_load_raises_load_error_for_unparseable_content(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")

    try:
        ReferenceSnapshot.load(path)
        assert False, "expected LoadError"
    except bpx_gateway.LoadError:
        pass
