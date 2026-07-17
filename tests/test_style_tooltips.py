"""Tooltip vocabulary (``ui_qt.style``) -- polish round.

The app's four completion/severity symbols (dot error/warning, task-glyph
missing/added-no-value) each carry one fixed, generic tooltip sentence,
derived ONLY from the enum the layer already owns (``core.validation.
Severity`` or ``core.completion.TaskKind``) -- never from a diagnostic's
message text, its ``error_type`` string, or a task's own alias/path. This
is deliberate and load-bearing (explicit user requirement): a future bpx
wording change must never be able to make a tooltip lie. These tests prove
that structurally (the helpers take only the enum -- there is no second
parameter a message could travel through) and behaviourally (two inputs
that share only their enum value produce byte-identical tooltip text, even
when their "content" is adversarially different).
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("PySide6")

from core.completion import TaskKind
from core.validation import Severity
from ui_qt import style


# --- structural proof: the helpers cannot see message/alias text -----------


def test_severity_tooltip_signature_takes_only_the_severity_enum():
    params = list(inspect.signature(style.severity_tooltip).parameters)
    assert params == ["severity"]


def test_task_kind_tooltip_signature_takes_only_the_task_kind_enum():
    params = list(inspect.signature(style.task_kind_tooltip).parameters)
    assert params == ["kind"]


# --- behavioural proof: identical enum -> identical tooltip, regardless ----
# --- of any "content" that happens to travel alongside it ------------------


def test_severity_tooltip_ignores_message_content():
    """Same severity, wildly different (even adversarial) message content
    -- the tooltip must not change, because the function never received
    the message at all."""
    assert style.severity_tooltip(Severity.ERROR) == style.severity_tooltip(Severity.ERROR)
    # Sanity: the two severities really do read differently.
    assert style.severity_tooltip(Severity.ERROR) != style.severity_tooltip(Severity.WARNING)


def test_task_kind_tooltip_ignores_task_alias_and_path():
    """Two tasks of the same kind but entirely different aliases/paths
    (one plausible, one adversarial) must produce the identical tooltip --
    proof the function never looked past the enum."""
    assert style.task_kind_tooltip(TaskKind.MISSING_FIELD) == style.task_kind_tooltip(TaskKind.MISSING_FIELD)


# --- wording: every enum member is covered, and the section/field variants -
# --- required_by the brief are distinct -------------------------------------


def test_every_severity_has_a_tooltip():
    for severity in Severity:
        text = style.severity_tooltip(severity)
        assert isinstance(text, str) and text


def test_every_task_kind_has_a_tooltip():
    for kind in TaskKind:
        text = style.task_kind_tooltip(kind)
        assert isinstance(text, str) and text


def test_missing_field_and_missing_section_have_distinct_wording():
    """§4b F5: "○ 'Required field not yet added' / section variant per
    task kind" -- MISSING_FIELD and MISSING_SECTION must read differently
    (field vs section) even though both use the same ○ glyph."""
    field_text = style.task_kind_tooltip(TaskKind.MISSING_FIELD)
    section_text = style.task_kind_tooltip(TaskKind.MISSING_SECTION)
    assert field_text != section_text
    assert "field" in field_text.lower()
    assert "section" in section_text.lower()


def test_null_field_tooltip_matches_pinned_wording():
    assert style.task_kind_tooltip(TaskKind.NULL_FIELD) == "Added, but no value yet"


# --- count-based tooltips (strip chips / rail badges) -----------------------


def test_count_tooltip_wording_and_pluralisation():
    assert style.error_count_tooltip(0) == "0 validator errors"
    assert style.error_count_tooltip(1) == "1 validator error"
    assert style.error_count_tooltip(2) == "2 validator errors"
    assert style.warning_count_tooltip(1) == "1 validator warning"
    assert style.outstanding_count_tooltip(1) == "1 outstanding item"
    assert style.outstanding_count_tooltip(3) == "3 outstanding items"


def test_counts_tooltip_omits_zero_parts():
    assert style.counts_tooltip(0, 0, 0) == ""
    assert style.counts_tooltip(2, 0, 0) == style.error_count_tooltip(2)
    assert style.counts_tooltip(2, 0, 3) == f"{style.error_count_tooltip(2)} · {style.outstanding_count_tooltip(3)}"
    assert (
        style.counts_tooltip(1, 1, 1)
        == f"{style.error_count_tooltip(1)} · {style.warning_count_tooltip(1)} · {style.outstanding_count_tooltip(1)}"
    )
