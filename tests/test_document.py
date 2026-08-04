"""Tests for the document model, including opening invalid files."""

from __future__ import annotations

from core.document import BPXDocument


def test_valid_document(valid_spm_bytes):
    document = BPXDocument.from_bytes(valid_spm_bytes, "spm_example_valid.json")
    assert document.is_valid is True
    assert document.error_count == 0
    assert document.find(("Parameterisation", "Cell")) is not None


def test_model_level_error_attaches_to_the_named_parameter(valid_spm_dict):
    """A bpx model-level check (material_check) reports loc == (), but names the
    parameter in its message. The error must land on that parameter -- so its
    badge and Issues tab show it -- not only at the document root.
    """
    import json

    path = (
        "State",
        "Initial conditions",
        "Initial hysteresis state: Positive electrode",
    )
    # The Positive electrode is blended, so a bare scalar here is invalid: the
    # field must be a dict keyed by the particle names. This is a real validator
    # error, surfaced verbatim -- not invented by the app.
    valid_spm_dict["State"]["Initial conditions"][
        "Initial hysteresis state: Positive electrode"
    ] = 1.0
    data = json.dumps(valid_spm_dict).encode("utf-8")
    document = BPXDocument.from_bytes(data, "blended.json")

    assert document.is_valid is False
    parameter = document.find_parameter(path)
    assert parameter is not None
    assert parameter.has_errors is True
    # The same diagnostic is not double-counted onto the document root.
    assert not any(issue in document.tree.issues for issue in parameter.issues)


def test_identity_reads_header_fields(valid_spm_dict):
    """A fully-populated Header yields all three identity fields."""
    import json

    data = json.dumps(valid_spm_dict).encode("utf-8")
    document = BPXDocument.from_bytes(data, "spm_example_valid.json")

    identity = document.identity
    assert identity.title == "Minimal valid SPM example"
    assert identity.model == "SPM"
    assert identity.bpx_version == "1.0.0"


def test_identity_missing_title_is_empty_string(valid_spm_dict):
    """A missing Title field falls back to an empty string, not a crash."""
    import json

    del valid_spm_dict["Header"]["Title"]
    data = json.dumps(valid_spm_dict).encode("utf-8")
    document = BPXDocument.from_bytes(data, "broken.json")

    identity = document.identity
    assert identity.title == ""
    assert identity.model == "SPM"
    assert identity.bpx_version == "1.0.0"


def test_identity_missing_header_is_all_empty_strings(valid_spm_dict):
    """An entirely missing Header yields empty strings for every field."""
    import json

    del valid_spm_dict["Header"]
    data = json.dumps(valid_spm_dict).encode("utf-8")
    document = BPXDocument.from_bytes(data, "broken.json")

    identity = document.identity
    assert identity.title == ""
    assert identity.model == ""
    assert identity.bpx_version == ""


def test_identity_coerces_non_string_bpx_version(valid_spm_dict):
    """A non-string BPX version value is coerced to str."""
    import json

    valid_spm_dict["Header"]["BPX"] = 1.0
    data = json.dumps(valid_spm_dict).encode("utf-8")
    document = BPXDocument.from_bytes(data, "broken.json")

    assert document.identity.bpx_version == "1.0"


def test_invalid_document_still_opens(valid_spm_dict):
    """The whole point: an invalid file still loads and remains explorable,
    rather than being rejected outright.

    Re-baselined for bpx 1.1.1: this used to parametrize over the nmc/lfp
    fixtures, which failed validation on legacy deprecated-field errors
    (``Cell.'Initial temperature [K]'``/``'Ambient temperature [K]'``); bpx
    1.1.1 auto-converts those cleanly now (probed directly against the real
    validator -- both open with zero errors), so they no longer demonstrate
    this. A minimal document with a garbage-typed ``Cell`` section is built
    here instead, which is still, genuinely invalid.
    """
    import json

    raw = valid_spm_dict
    raw["Parameterisation"]["Cell"] = "not a section"
    data = json.dumps(raw).encode("utf-8")

    document = BPXDocument.from_bytes(data, "invalid_probe.json")
    assert document.is_valid is False
    assert document.error_count > 0
    assert document.tree.children


def test_missing_field_attaches_to_owning_section_not_sibling_leaf(fixtures_dir):
    """A missing required field must be flagged on the section that lacks it.

    Regression test for a presentation-layer mis-mapping: when a required
    field is absent, the validator names the section that lacks it. That
    diagnostic must land on the owning section, and must never be misattached
    to a same-named sibling field that happens to be present and valid
    elsewhere in the tree.

    Scenario: remove "Reaction rate constant [mol.m-2.s-1]" from the Negative
    electrode (making it a missing required field) while the Positive electrode
    keeps its own present, valid value.
    """
    import json

    raw = json.loads((fixtures_dir / "nmc_pouch_cell_BPX.json").read_text("utf-8"))
    del raw["Parameterisation"]["Negative electrode"]["Reaction rate constant [mol.m-2.s-1]"]
    raw["Parameterisation"]["Positive electrode"]["Reaction rate constant [mol.m-2.s-1]"] = 444
    data = json.dumps(raw).encode("utf-8")

    document = BPXDocument.from_bytes(data, "broken.json")

    # The missing field is reported on the Negative electrode section, as a
    # single "Field required" error.
    negative_electrode = document.find(("Parameterisation", "Negative electrode"))
    assert negative_electrode is not None
    required_errors = [
        issue for issue in negative_electrode.issues if issue.message == "Field required"
    ]
    assert len(required_errors) == 1

    # The Positive electrode's present, valid parameter is left untouched.
    positive_parameter = document.find_parameter(
        ("Parameterisation", "Positive electrode", "Reaction rate constant [mol.m-2.s-1]")
    )
    assert positive_parameter is not None
    assert positive_parameter.value == 444
    assert not positive_parameter.has_errors


def test_issue_attached_to_node(valid_spm_bytes):
    import json

    raw = json.loads(valid_spm_bytes)
    raw["Parameterisation"]["Cell"]["Upper voltage cut-off [V]"] = "oops"
    data = json.dumps(raw).encode("utf-8")
    document = BPXDocument.from_bytes(data, "broken.json")

    node = document.find(("Parameterisation", "Cell"))
    assert node is not None
    assert node.has_errors

    parameter = document.find_parameter(
        ("Parameterisation", "Cell", "Upper voltage cut-off [V]")
    )
    assert parameter is not None
    assert parameter.has_errors
