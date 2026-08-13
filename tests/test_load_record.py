"""Tests for ``core.load_record`` -- the load-time facts record. No UI: the
record is a pure core value object."""

from __future__ import annotations

import copy
import json

from core.bpx_gateway import CheckReach
from core.document import BPXDocument
from core.load_record import LoadRecord


def _capture(data, filename, path=None):
    """Load *data* the way ``AppState.open`` does, then capture its record."""
    document = BPXDocument.from_bytes(data, filename)
    return LoadRecord.capture(data, document, path=path)


def test_capture_records_disk_facts(spm_workfile):
    data = spm_workfile.read_bytes()
    record = _capture(data, spm_workfile.name, path=spm_workfile)
    stat = spm_workfile.stat()
    assert record.fmt == "json"
    assert record.is_legacy is False
    assert record.checked is CheckReach.COMPLETE
    assert record.has_yaml_comments is False
    assert record.size_bytes == stat.st_size == len(data)
    assert record.mtime == stat.st_mtime


def test_capture_without_path_has_no_disk_facts(valid_spm_bytes):
    """A document with no backing file (pasted bytes, a New scaffold) has
    no disk facts to state -- None, never a guess."""
    record = _capture(valid_spm_bytes, "spm_example_valid.json")
    assert record.size_bytes is None
    assert record.mtime is None


def test_capture_carries_the_loaders_format(valid_spm_bytes):
    """``fmt`` is the format the load actually used (the document's own
    record), not a re-derivation here."""
    record = _capture(b"Header:\n  Model: SPM\n", "thing.yaml")
    assert record.fmt == "yaml"
    assert _capture(valid_spm_bytes, "spm_example_valid.json").fmt == "json"


def test_capture_flags_legacy_v0_file(fixtures_dir):
    """The real v0.x fixture (Header.BPX = 0.1) is detected, while the raw
    dict the app renders stays unconverted -- the fact the legacy-open
    prompt needs."""
    path = fixtures_dir / "nmc_pouch_cell_BPX.json"
    data = path.read_bytes()
    record = _capture(data, path.name, path=path)
    assert record.is_legacy is True


def test_capture_checked_is_how_far_checking_reached(valid_spm_dict):
    """``checked`` snapshots the document's validation reach at load: a
    Header abort loads as HEADER, not as an absence of errors."""
    broken = copy.deepcopy(valid_spm_dict)
    broken["Header"]["Model"] = "XFN"
    record = _capture(json.dumps(broken).encode("utf-8"), "broken.json")
    assert record.checked is CheckReach.HEADER


def test_yaml_comments_detected():
    data = b"# top comment\nHeader:\n  Model: SPM  # trailing comment\n"
    record = _capture(data, "thing.yaml")
    assert record.fmt == "yaml"
    assert record.has_yaml_comments is True


def test_yaml_hash_inside_scalars_is_not_a_comment():
    """A ``#`` inside a quoted scalar, a plain-scalar URL fragment, or a
    block scalar's body is data, not a comment -- the record must not warn
    about comments a save would in fact preserve."""
    data = (
        b"Header:\n"
        b'  Title: "see # not a comment"\n'
        b"  Description: |\n"
        b"    block body with # hash\n"
        b"  References: https://doi.org/10.1000/xyz#fragment\n"
    )
    record = _capture(data, "thing.yaml")
    assert record.has_yaml_comments is False


def test_yaml_comment_beside_hashful_data_is_still_detected():
    """One real comment is enough, even when the same document also
    carries ``#`` characters inside its data."""
    data = (
        b"Header:\n"
        b'  Title: "keep # this"  # but this is a comment\n'
    )
    record = _capture(data, "thing.yaml")
    assert record.has_yaml_comments is True


def test_json_never_reports_comments():
    """JSON has no comments; a ``#`` inside a JSON string must not put a
    false comment warning on the record."""
    data = b'{"Header": {"Title": "# not a comment"}}'
    record = _capture(data, "thing.json")
    assert record.has_yaml_comments is False
