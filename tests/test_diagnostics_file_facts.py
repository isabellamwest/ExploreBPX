"""The diagnostics stream's file-facts group: the load-time facts a person
needs before trusting the diagnostics beneath, restated in the stream's own
fold-header grammar ahead of every bucket.

Two layers: :func:`~ui_qt.file_facts.file_facts` itself (pure, no Qt --
every fact/order/wording combination) and the group as it actually renders
in the live stream (ordering, the everyday-clean-file absence, chip
exemption, fold/persist, the New-scaffold case).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from explore_bpx.core.bpx_gateway import BPX_VERSION, CheckReach
from explore_bpx.core.load_record import LoadRecord
from explore_bpx.ui_qt.file_facts import FileFact, file_facts


def _record(*, is_legacy: bool = False, has_yaml_comments: bool = False, fmt: str = "json") -> LoadRecord:
    """A minimal ``LoadRecord`` -- only ``is_legacy``/``has_yaml_comments``
    matter to :func:`file_facts`; ``checked`` is the load-time snapshot
    (unrelated -- the live ``document.validation_reach`` is its own
    argument), so it is fixed to COMPLETE here regardless of the scenario."""
    return LoadRecord(fmt=fmt, is_legacy=is_legacy, checked=CheckReach.COMPLETE, has_yaml_comments=has_yaml_comments)


# ---------------------------------------------------------------------------
# Pure derivation (no Qt): every fact, its wording, and the signed order.
# ---------------------------------------------------------------------------


def test_no_facts_for_a_clean_complete_load():
    record = _record()
    assert file_facts("clean.json", record, CheckReach.COMPLETE, "1.0.0") == ()


def test_no_facts_with_no_record_and_complete_reach():
    """A New scaffold with no record but a COMPLETE reach (hypothetically)
    would add nothing either -- reach is the only record-less fact, and
    COMPLETE names none."""
    assert file_facts("untitled.json", None, CheckReach.COMPLETE, "") == ()


def test_legacy_fact_names_the_files_own_declared_version():
    record = _record(is_legacy=True)
    facts = file_facts("legacy.json", record, CheckReach.COMPLETE, "0.4")
    assert facts == (
        FileFact(
            f"Checked as a BPX {BPX_VERSION} conversion",
            "legacy.json is BPX 0.4 \u00b7 the editor shows the file as it is on disk",
        ),
    )


def test_legacy_fact_falls_back_when_the_file_declares_no_version():
    record = _record(is_legacy=True)
    facts = file_facts("legacy.json", record, CheckReach.COMPLETE, "")
    assert facts[0].sub == "legacy.json is a BPX 0.x file \u00b7 the editor shows the file as it is on disk"


def test_reach_facts_apply_even_with_no_record():
    assert file_facts("untitled.json", None, CheckReach.HEADER, "") == (
        FileFact("Checking stopped at Header", "Nothing below it was checked"),
    )
    assert file_facts("untitled.json", None, CheckReach.PARAMETERISATION, "") == (
        FileFact("Checking stopped at Parameterisation", "State and Validation were not checked"),
    )
    assert file_facts("untitled.json", None, CheckReach.NOT_RUN, "") == (
        FileFact("Checking did not run", "bpx stopped before judging anything"),
    )


def test_comments_fact_requires_a_real_record():
    record = _record(fmt="yaml", has_yaml_comments=True)
    assert file_facts("notes.yaml", record, CheckReach.COMPLETE, "") == (
        FileFact("Comments will not survive saving", "Saving rewrites the whole file"),
    )


def test_facts_render_in_signed_order_legacy_then_reach_then_comments():
    record = _record(fmt="yaml", is_legacy=True, has_yaml_comments=True)
    facts = file_facts("legacy.yaml", record, CheckReach.HEADER, "0.4")
    assert [fact.headline for fact in facts] == [
        f"Checked as a BPX {BPX_VERSION} conversion",
        "Checking stopped at Header",
        "Comments will not survive saving",
    ]


# ---------------------------------------------------------------------------
# The live stream: ordering, absence, chip exemption, fold/persist.
# ---------------------------------------------------------------------------


def test_legacy_file_shows_the_group_first_with_the_legacy_fact(app_driver, fixtures_dir):
    d = app_driver
    d.open_as_is(fixtures_dir / "nmc_pouch_cell_BPX.json")

    headers = d.diagnostics_stream_headers()
    assert headers[0] == "nmc_pouch_cell_BPX.json  1 note"
    assert d.diagnostics_file_facts_header() == "nmc_pouch_cell_BPX.json  1 note"

    facts = d.diagnostics_file_fact_texts()
    assert len(facts) == 1
    assert facts[0].startswith(f"Checked as a BPX {BPX_VERSION} conversion")


def test_yaml_comments_shows_the_comments_fact_with_a_singular_suffix(app_driver, valid_spm_dict, tmp_path):
    import yaml as yaml_module

    work = tmp_path / "commented.yaml"
    work.write_text(
        "# calibration notes\n" + yaml_module.safe_dump(valid_spm_dict),
        encoding="utf-8",
    )

    d = app_driver
    d.open(work)

    assert d.diagnostics_file_facts_header() == "commented.yaml  1 note"
    assert d.diagnostics_file_fact_texts() == ["Comments will not survive saving\nSaving rewrites the whole file"]


def test_clean_complete_document_shows_no_group(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)

    assert d.diagnostics_file_facts_header() is None
    assert d.diagnostics_file_fact_texts() == []


def test_group_survives_every_chip_toggled_off(app_driver, fixtures_dir):
    """The group is exempt from the three filter chips (like the clear
    line/all-clear row) -- it renders regardless of chip state."""
    d = app_driver
    d.open_as_is(fixtures_dir / "nmc_pouch_cell_BPX.json")

    d.diagnostics_toggle_chip("errors")
    d.diagnostics_toggle_chip("warnings")
    d.diagnostics_toggle_chip("outstanding")

    assert d.diagnostics_file_facts_header() == "nmc_pouch_cell_BPX.json  1 note"
    assert len(d.diagnostics_file_fact_texts()) == 1


def test_group_folds_on_click_and_survives_a_refresh(app_driver, fixtures_dir):
    """Folding hides the rows but the header (and its "N notes" suffix)
    stays -- the fact of how many notes there are never disappears; the
    fold state persists across an ordinary refresh like any other
    section's."""
    d = app_driver
    d.open_as_is(fixtures_dir / "nmc_pouch_cell_BPX.json")
    assert d.diagnostics_file_fact_texts() != []

    d.diagnostics_fold_section("nmc_pouch_cell_BPX.json")

    assert d.diagnostics_file_facts_header() == "nmc_pouch_cell_BPX.json  1 note"
    assert d.diagnostics_file_fact_texts() == []

    # An as-is legacy session is read-only, so the "ordinary refresh" is
    # driven directly rather than by an edit.
    d._w._refresh_all()

    assert d.diagnostics_file_facts_header() == "nmc_pouch_cell_BPX.json  1 note"
    assert d.diagnostics_file_fact_texts() == []


def test_new_scaffold_shows_the_parameterisation_reach_fact(app_driver):
    """Every fresh New scaffold aborts at Parameterisation -- the
    reach fact shows under "untitled.json" even with no ``LoadRecord`` at
    all."""
    d = app_driver
    d._w._new("SPM")

    assert d.diagnostics_file_facts_header() == "untitled.json  1 note"
    assert d.diagnostics_file_fact_texts() == [
        "Checking stopped at Parameterisation\nState and Validation were not checked"
    ]
