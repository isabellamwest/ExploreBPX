"""Tests for the bundled database-examples library (core layer, no Qt)."""

from __future__ import annotations

from core import example_library


def test_list_example_runs_finds_both_documents():
    runs = example_library.list_example_runs()
    assert {r.document_id for r in runs} == {
        "bpx_official/nmc_pouch_cell_BPX",
        "bpx_official/nmc_pouch_cell_BPX_SPM",
    }
    assert {r.run_name for r in runs} == {"C/20 discharge", "1C discharge"}
    assert len(runs) == 4


def test_run_metadata_matches_the_bundled_files():
    by_id = {r.id: r for r in example_library.list_example_runs()}

    base = by_id["bpx_official/nmc_pouch_cell_BPX::C/20 discharge"]
    assert base.model == "DFN"
    assert base.point_count == 76
    assert base.has_temperature is True
    assert "NMC111|graphite" in base.document_title
    assert base.short_title == "NMC pouch cell"

    spm = by_id["bpx_official/nmc_pouch_cell_BPX_SPM::1C discharge"]
    assert spm.model == "SPM"
    assert spm.point_count == 38
    assert spm.has_temperature is True
    assert spm.short_title == "NMC pouch cell (SPM)"


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
