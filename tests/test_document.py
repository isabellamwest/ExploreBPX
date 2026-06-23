"""Tests for the document model, including opening invalid files."""

from __future__ import annotations

import pytest

from core.document import BPXDocument


def test_valid_document(valid_spm_bytes):
    document = BPXDocument.from_bytes(valid_spm_bytes, "spm_example_valid.json")
    assert document.is_valid is True
    assert document.error_count == 0
    assert document.find(("Parameterisation", "Cell")) is not None


@pytest.mark.parametrize(
    "filename",
    ["lfp_18650_cell_BPX.json", "nmc_pouch_cell_BPX.json"],
)
def test_invalid_files_still_open(examples_dir, filename):
    data = (examples_dir / filename).read_bytes()
    document = BPXDocument.from_bytes(data, filename)
    # The whole point: invalid files load and remain explorable.
    assert document.is_valid is False
    assert document.error_count > 0
    assert document.tree.children


def test_issue_attached_to_node(valid_spm_bytes):
    import json

    raw = json.loads(valid_spm_bytes)
    raw["Parameterisation"]["Cell"]["Upper voltage cut-off [V]"] = "oops"
    data = json.dumps(raw).encode("utf-8")
    document = BPXDocument.from_bytes(data, "broken.json")

    node = document.find(("Parameterisation", "Cell", "Upper voltage cut-off [V]"))
    assert node is not None
    assert node.has_errors
