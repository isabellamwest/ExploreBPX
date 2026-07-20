"""Tests for the reference-Validation-run library (core layer, no Qt): the
bundled About:Energy sample cells, and ``load_reference_document`` for a
user-chosen file."""

from __future__ import annotations

import json

import pytest

from core import example_library
from core.bpx_gateway import LoadError

_RUN_NAMES = {"C/20 discharge", "C/2 discharge", "1C discharge", "2C discharge", "Drive cycle"}


def test_list_example_runs_finds_both_documents():
    runs = example_library.list_example_runs()
    assert {r.document_id for r in runs} == {
        "about_energy/nmc_pouch_cell",
        "about_energy/lfp_18650_cell",
    }
    assert {r.run_name for r in runs} == _RUN_NAMES
    assert len(runs) == 10  # two documents x five runs each


def test_run_metadata_matches_the_bundled_files():
    by_id = {r.id: r for r in example_library.list_example_runs()}

    nmc = by_id["about_energy/nmc_pouch_cell::C/20 discharge"]
    assert nmc.model == "DFN"
    assert nmc.point_count == 1000
    assert nmc.has_temperature is False
    assert "NMC111|graphite" in nmc.document_title
    assert nmc.short_title == "NMC pouch cell"

    lfp = by_id["about_energy/lfp_18650_cell::1C discharge"]
    assert lfp.model == "DFN"
    assert lfp.point_count == 1000
    assert lfp.has_temperature is False
    assert "LFP|graphite" in lfp.document_title
    assert lfp.short_title == "LFP 18650 cell"


def test_load_example_run_returns_arrays_matching_the_listed_point_count():
    runs = example_library.list_example_runs()
    for run in runs:
        data = example_library.load_example_run(run.id)
        assert set(data) >= {"Time [s]", "Current [A]", "Voltage [V]"}
        assert len(data["Time [s]"]) == run.point_count
        assert len(data["Current [A]"]) == run.point_count
        assert len(data["Voltage [V]"]) == run.point_count
        if run.has_temperature:
            assert len(data["Temperature [K]"]) == run.point_count


def test_ids_round_trip_through_double_colon_separator():
    for run in example_library.list_example_runs():
        document_id, run_name = run.id.split("::", 1)
        assert document_id == run.document_id
        assert run_name == run.run_name


# ---------------------------------------------------------------------------
# load_reference_document: the Validation slice of a user-chosen BPX file
# ---------------------------------------------------------------------------


def test_load_reference_document_returns_runs_and_data_prefixed_with_document_id():
    payload = json.dumps(
        {
            "Header": {"BPX": "0.1.0", "Title": "My Test Cell", "Model": "DFN"},
            "Validation": {
                "Run A": {
                    "Time [s]": [0, 1, 2],
                    "Current [A]": [-2.0, -2.0, -2.0],
                    "Voltage [V]": [4.2, 4.1, 4.0],
                },
            },
        }
    ).encode("utf-8")

    document = example_library.load_reference_document(payload, "my_cell.json", "file:1")

    assert document.label == "my_cell"
    assert document.title == "My Test Cell"
    assert document.model == "DFN"
    assert len(document.runs) == 1
    run = document.runs[0]
    assert run.id == "file:1::Run A"
    assert run.document_id == "file:1"
    assert run.run_name == "Run A"
    assert run.point_count == 3
    assert document.data["Run A"]["Time [s]"] == [0, 1, 2]


def test_load_reference_document_with_no_validation_section_yields_zero_runs():
    payload = json.dumps({"Header": {"Title": "No runs here"}}).encode("utf-8")

    document = example_library.load_reference_document(payload, "empty.json", "file:2")

    assert document.runs == ()
    assert document.data == {}


def test_load_reference_document_raises_load_error_on_garbage_bytes():
    with pytest.raises(LoadError):
        example_library.load_reference_document(b"not { valid json", "bad.json", "file:3")
