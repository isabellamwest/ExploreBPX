"""Tests for the bundled PyBaMM-derived reference library adapter.

The load-bearing test here is the validity pin: every bundled reference file
must parse VALID through the app's own gateway (i.e. against the pinned
``bpx``). A bpx upgrade that invalidates a bundled file must fail here, not
surface as a mysteriously red reference in the UI -- the fix is regenerating
the library with ``scripts/generate_reference_library.py``, never editing
the files by hand.
"""

from __future__ import annotations

import pytest

from core import bpx_gateway, reference_library


def test_lists_the_bundled_sets_in_curated_order():
    sets = reference_library.list_reference_sets()
    assert [s.id.split("/", 1)[1] for s in sets] == [
        "chen2020",
        "prada2013",
        "ai2020",
        "mohtat2020",
    ]


def test_every_set_carries_full_picker_metadata():
    for reference in reference_library.list_reference_sets():
        assert reference.id.startswith("pybamm/")
        assert reference.title
        assert reference.short_title
        assert reference.model == "DFN"
        # The description is the honesty label: every generated file must
        # declare itself a reference artifact, not simulation-grade data.
        assert "Reference artifact" in reference.description


def test_every_bundled_file_is_valid_under_the_pinned_bpx():
    for reference in reference_library.list_reference_sets():
        raw = reference_library.load_reference_raw(reference.id)
        result = bpx_gateway.validate(raw)
        assert result.is_valid, (
            f"{reference.id} no longer validates under bpx {bpx_gateway.BPX_VERSION}: "
            f"{[issue.message for issue in result.issues]!r} -- regenerate the "
            "library with scripts/generate_reference_library.py"
        )
        assert result.completed is True


def test_load_returns_an_isolated_copy():
    first = reference_library.load_reference_raw("pybamm/chen2020")
    first["Header"]["Title"] = "mutated"
    second = reference_library.load_reference_raw("pybamm/chen2020")
    assert second["Header"]["Title"] != "mutated"


def test_unknown_id_raises_key_error():
    with pytest.raises(KeyError):
        reference_library.load_reference_raw("pybamm/nope")
    with pytest.raises(KeyError):
        reference_library.load_reference_raw("about_energy/nmc_pouch_cell")
