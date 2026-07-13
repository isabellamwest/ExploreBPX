"""Behavioural backbone: application behaviour verified independently of the UI.

These tests exercise complete workflows through the frontend-agnostic state and
core layers (``AppState`` / ``DocumentSession`` / ``BPXDocument``). They contain
no Qt or ``ui_qt`` imports, so they continue to pass through almost any UI
refactor -- they protect *what the application does*, not how it is presented.

The thin UI wiring on top of this behaviour is covered by
``test_workflows_ui.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.parameter_types import ParameterKind
from state.app_state import AppState

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
_MODEL = ("Header", "Model")


def _open(path: Path) -> AppState:
    state = AppState()
    state.open(path)
    return state


# ---------------------------------------------------------------------------
# Flagship: open -> select -> edit -> validation updates -> issues update
# ---------------------------------------------------------------------------

def test_edit_lifecycle_updates_validation_dirty_and_issues(spm_workfile):
    """The core edit workflow: a live preview never mutates the document, a
    committed invalid value fails validation and attaches a navigable issue,
    and a subsequent valid commit clears it."""
    state = _open(spm_workfile)
    session = state.active
    assert session.document.is_valid
    assert not session.dirty

    # Selection resolves the parameter without mutating anything.
    session.select(_CAPACITY[:-1])
    session.select_parameter(_CAPACITY)
    assert session.selected_parameter().label == "Nominal cell capacity [A.h]"

    # Live preview of an invalid draft: reports invalid, leaves the document
    # untouched (still valid, raw unchanged).
    before = json.dumps(session.document.raw, sort_keys=True)
    preview = session.preview_value(_CAPACITY, "not-a-number")
    assert not preview.is_valid
    assert session.document.is_valid
    assert json.dumps(session.document.raw, sort_keys=True) == before

    # Commit the invalid value: document becomes invalid, dirty, and the issue
    # is attached to the parameter and discoverable via iter_issues.
    session.apply_value(_CAPACITY, "not-a-number")
    assert not session.document.is_valid
    assert session.dirty
    assert session.document.find_parameter(_CAPACITY).has_errors
    # The issue is discoverable and resolves back to the parameter it came from.
    resolved = [
        session.document.find_best_parameter(nav)
        for _, nav in session.document.iter_issues()
    ]
    assert session.document.find_parameter(_CAPACITY) in resolved

    # Repair it: document is valid again.
    session.apply_value(_CAPACITY, 5.0)
    assert session.document.is_valid
    assert not session.document.find_parameter(_CAPACITY).has_errors


def test_preview_parameter_issues_excludes_document_level_diagnostics(
    warning_only_bpx_path, tmp_path
):
    """A document-level warning must never colour an unrelated parameter's
    validity badge while the user types.

    ``warning_legacy_bpx_float.json`` carries a Header/BPX deprecation warning
    that attaches to no parameter. Previewing a perfectly valid edit to an
    unrelated parameter must therefore report *no* issues for that parameter,
    even though the document as a whole still has one.
    """
    workfile = tmp_path / "warning.json"
    workfile.write_bytes(warning_only_bpx_path.read_bytes())

    session = _open(workfile).active
    assert session.document.warning_count == 1, "fixture must carry a document-level warning"
    assert not session.document.find_parameter(_CAPACITY).issues

    # The document-wide preview still sees the Header warning ...
    assert len(session.preview_value(_CAPACITY, 5.0).issues) == 1
    # ... but the parameter-scoped preview does not: the badge stays Valid.
    assert session.preview_parameter_issues(_CAPACITY, 5.0) == []

    # A genuinely invalid draft for this parameter is still reported on it.
    assert session.preview_parameter_issues(_CAPACITY, "not-a-number")


def test_committed_invalid_value_resolves_to_a_navigable_parameter(spm_workfile):
    """An issue's navigation path must resolve back to the parameter it came
    from -- the resolution that powers every 'jump to issue' interaction."""
    state = _open(spm_workfile)
    session = state.active
    session.apply_value(_MODEL, "not-a-model")

    issues = session.document.iter_issues()
    assert issues, "expected at least one validation issue"
    _, nav_path = issues[0]
    assert session.document.find_best_parameter(nav_path) is not None


def test_recovery_from_invalid_edit_keeps_parameter_editable(spm_workfile):
    """Committing a string to a numeric field must not trap the user: the
    parameter stays an editable kind so the value can be repaired."""
    state = _open(spm_workfile)
    session = state.active
    session.apply_value(_CAPACITY, "still-not-a-number")

    parameter = session.document.find_parameter(_CAPACITY)
    assert parameter.has_errors
    assert parameter.kind in {
        ParameterKind.SCALAR,
        ParameterKind.INTEGER,
        ParameterKind.FUNCTION,
    }

    session.apply_value(_CAPACITY, 5.0)
    assert session.document.is_valid


# ---------------------------------------------------------------------------
# Invalid documents
# ---------------------------------------------------------------------------

def test_invalid_document_opens_and_stays_explorable(invalid_bpx_path):
    """A schema-invalid file still opens, reports errors, and keeps a navigable
    tree with issues that resolve to a location."""
    state = _open(invalid_bpx_path)
    document = state.active.document
    assert not document.is_valid
    assert document.error_count > 0
    assert document.tree.children  # tree still built
    issues = document.iter_issues()
    assert issues
    # Every issue resolves to a node or parameter (or the document root).
    for _, nav_path in issues:
        resolved = (
            document.find_best_parameter(nav_path)
            or document.find_best(nav_path)
            or document.tree
        )
        assert resolved is not None


# ---------------------------------------------------------------------------
# Save (format + dirty semantics not already covered by test_app_state)
# ---------------------------------------------------------------------------

def test_save_infers_json_from_extension(spm_workfile):
    state = _open(spm_workfile)
    state.active.apply_value(_MODEL, "DFN")
    state.active.save()
    assert json.loads(spm_workfile.read_text("utf-8"))["Header"]["Model"] == "DFN"
    assert not state.active.dirty


def test_save_infers_yaml_from_extension(spm_workfile, tmp_path):
    import yaml

    out = tmp_path / "saved.yaml"
    state = _open(spm_workfile)
    state.active.backing_file = out
    state.active.apply_value(_MODEL, "DFN")
    state.active.save()
    assert yaml.safe_load(out.read_text("utf-8"))["Header"]["Model"] == "DFN"


def test_save_without_backing_file_raises(spm_workfile):
    state = _open(spm_workfile)
    state.active.backing_file = None
    with pytest.raises(ValueError):
        state.active.save()
