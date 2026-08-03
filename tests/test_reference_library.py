"""Tests for the bundled PyBaMM-derived reference library adapter.

The load-bearing test here is the validity pin: every bundled reference file
must parse VALID through the app's own gateway (i.e. against the pinned
``bpx``). A bpx upgrade that invalidates a bundled file must fail here, not
surface as a mysteriously red reference in the UI -- the fix is regenerating
the library with ``scripts/generate_reference_library.py``, never editing
the files by hand.
"""

from __future__ import annotations

import re

import pytest

from core import bpx_gateway, reference_library

#: Chemistry designations, mirroring the generator's ``CHEMISTRY_FAMILIES``.
#: Repeated rather than imported: ``scripts/`` is a dev-time tool that imports
#: ``pybamm``, which is deliberately not an app or test dependency.
_CHEMISTRY = re.compile(r"(?:NMC|NCA|LFP|LCO|LMO|LTO)\d*")


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
        # ...and every set must name the publication its values come from,
        # so attribution never depends on reading NOTICE.md.
        assert "doi:" in reference.references


def test_the_curated_short_titles_agree_with_the_files_own_titles():
    """A hand-curated picker label that drifts from the document it labels is
    a transparency bug: the user picks by the short title and docks the file.
    Compare on the chemistry/cell token, the only claim both make."""
    for reference in reference_library.list_reference_sets():
        cell = reference.short_title.partition("(")[2].rstrip(")")
        for token in cell.split():
            assert token in reference.title, (
                f"{reference.id}: picker label says {cell!r} but the document "
                f"is titled {reference.title!r}"
            )


def test_the_notice_agrees_with_the_documents_it_describes():
    """``NOTICE.md`` is the licence and provenance record, and its chemistry
    claims are hand-written -- by the same hand, from the same reading, that
    writes the curated picker labels. When that reading is wrong every copy
    is wrong together, so pin the copies to the generated documents.

    The generator's own ``_verify_chemistry`` gate is what pins the reading
    to PyBaMM, but it only runs offline; this runs on every commit.
    """
    notice = (reference_library._ASSETS / "NOTICE.md").read_text(encoding="utf-8")
    for reference in reference_library.list_reference_sets():
        stem = reference.id.split("/", 1)[1]
        bullet = next(
            (chunk for chunk in notice.split("* `") if chunk.startswith(f"{stem}.json`")),
            None,
        )
        assert bullet is not None, f"NOTICE.md documents no source for {stem}.json"
        assert set(_CHEMISTRY.findall(bullet)) == set(_CHEMISTRY.findall(reference.title)), (
            f"{stem}: NOTICE.md and the document's own Title disagree on chemistry"
        )


def test_mohtat2020_is_the_nmc532_cell_pybamm_documents():
    """Regression pin: this set was mislabelled NMC111 in the picker, the
    document Title and NOTICE.md. PyBaMM documents it as a graphite/NMC532
    pouch cell (doi:10.1149/1945-7111/aba5d1)."""
    mohtat = next(
        s for s in reference_library.list_reference_sets() if s.id.endswith("mohtat2020")
    )
    assert "NMC532" in mohtat.title and "NMC532" in mohtat.short_title
    assert "NMC111" not in mohtat.title


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
