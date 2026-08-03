"""Validator diagnostic model.

Provides lossless wrappers around the diagnostic objects produced by the BPX
validation pipeline.  Each concrete type preserves the original object exactly
as the pipeline returned it and exposes a stable typed interface over it.

Navigation, tree-matching and presentation are derived elsewhere; this module
only captures and exposes validator output.
"""

from __future__ import annotations

import warnings as _warnings
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Presentation-layer severity classification assigned by Explore_BPX."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class PydanticErrorDiagnostic:
    """Preserves a single Pydantic validation error exactly as returned by
    ``ValidationError.errors()``.

    Properties expose the validator's own fields through a stable typed API;
    no information is added, removed or reshaped.
    """

    raw_error: dict[str, Any]
    severity: Severity = Severity.ERROR

    @property
    def loc(self) -> tuple[str, ...]:
        """Original location tuple from the validator."""
        return tuple(str(part) for part in self.raw_error.get("loc", ()))

    @property
    def message(self) -> str:
        """Error message from the validator."""
        return self.raw_error.get("msg", "")

    @property
    def error_type(self) -> str:
        """Error type code (e.g. ``"extra_forbidden"``)."""
        return self.raw_error.get("type", "")

    @property
    def input(self) -> Any:
        """The value that failed validation."""
        return self.raw_error.get("input")

    @property
    def context(self) -> dict[str, Any] | None:
        """Validator context dict (e.g. allowed values, bounds)."""
        return self.raw_error.get("ctx")

    @property
    def documentation_url(self) -> str | None:
        """Link to validator documentation for this error type."""
        return self.raw_error.get("url")


@dataclass(frozen=True)
class PythonWarningDiagnostic:
    """Preserves a Python warning exactly as captured by
    ``warnings.catch_warnings()``.
    """

    raw_warning: _warnings.WarningMessage
    severity: Severity = Severity.WARNING

    @property
    def message(self) -> str:
        """Warning message as a string."""
        return str(self.raw_warning.message)


@dataclass(frozen=True)
class BPXExceptionDiagnostic:
    """Preserves an exception raised by the BPX validation pipeline that is not
    a ``pydantic.ValidationError`` (e.g. ``TypeError``, ``ValueError``).
    """

    raw_exception: BaseException
    severity: Severity = Severity.ERROR

    @property
    def message(self) -> str:
        """Exception message as a string."""
        return str(self.raw_exception)


# Type alias covering all diagnostics produced by the validation pipeline.
# New sources can be added here without changing the architectural principle.
ValidatorDiagnostic = PydanticErrorDiagnostic | PythonWarningDiagnostic | BPXExceptionDiagnostic


def issues_from_pydantic(errors: list[dict]) -> list[PydanticErrorDiagnostic]:
    """Wrap Pydantic error dicts as diagnostics, preserving all information."""
    return [PydanticErrorDiagnostic(raw_error=error) for error in errors]


def warnings_as_diagnostics(
    caught: list[_warnings.WarningMessage],
) -> list[PythonWarningDiagnostic]:
    """Wrap captured Python warnings as diagnostics, preserving all information."""
    return [PythonWarningDiagnostic(raw_warning=w) for w in caught]


# --- Display helpers --------------------------------------------------------
#
# A nullable ``FloatInt`` field holding a bad/``null`` value is a union of two
# branches (``float`` and ``int``), so pydantic raises once per branch --
# ``float_type`` *and* ``int_type`` for the exact same input (V5). Both are
# real, and neither is dropped from ``parameter.issues``/absorption/the
# validator's own output; these helpers only decide how many *rows* a UI
# paints for that one underlying problem. Display-only: callers pass the
# merged result to a widget, never back into ``core`` state.

#: The FloatInt union raises one error per branch, so a single bad value
#: draws a matched (float, int) pair. There are two variants, by *how* the
#: value is wrong: ``float_type``/``int_type`` for an empty or wrong-typed
#: value (V5, e.g. committed ``null`` or a list), and
#: ``float_parsing``/``int_parsing`` for a value of the right shape that
#: won't parse (a bad string typed into the field). Each is one underlying
#: problem; both collapse to their float branch's message ("Input should be
#: a valid number ..."). Keyed float→int so the merge always drops the int
#: branch, keeping the "number" wording.
_UNION_PAIRS = (("float_type", "int_type"), ("float_parsing", "int_parsing"))


def merge_union_pair(diagnostics: Sequence[ValidatorDiagnostic]) -> tuple[ValidatorDiagnostic, ...]:
    """Collapse each matched FloatInt union pair (:data:`_UNION_PAIRS`) to its
    single float-branch diagnostic ("Input should be a valid number") for
    display.

    *diagnostics* must already be scoped to one parameter (e.g.
    ``parameter.issues``, or every diagnostic absorbed by one Outstanding
    task) -- this never groups across parameters; see
    :func:`merge_union_pairs_by_location` for a mixed, multi-parameter list.
    Every diagnostic that isn't part of a complete pair passes through
    unchanged, in its original order.
    """
    types = {getattr(d, "error_type", None) for d in diagnostics}
    drop = {
        int_type
        for float_type, int_type in _UNION_PAIRS
        if float_type in types and int_type in types
    }
    if not drop:
        return tuple(diagnostics)
    return tuple(d for d in diagnostics if getattr(d, "error_type", None) not in drop)


def merge_union_pairs_by_location(
    items: Sequence[tuple[ValidatorDiagnostic, tuple[str, ...]]],
) -> tuple[tuple[ValidatorDiagnostic, tuple[str, ...]], ...]:
    """Apply :func:`merge_union_pair` across a list of ``(diagnostic,
    nav_path)`` pairs spanning many parameters (e.g. the Diagnostics page's
    Issues section, or a document's full diagnostic list).

    Groups by exact ``nav_path`` equality -- the float/int pair for one
    field always shares one nav_path (the validator's own union-branch tag is
    already stripped by the time a caller has a nav_path, see
    ``core.document._derive_nav_path``) -- merges within each group, and
    returns the result in original first-occurrence order.
    """
    groups: dict[tuple[str, ...], list[tuple[ValidatorDiagnostic, tuple[str, ...]]]] = {}
    order: list[tuple[str, ...]] = []
    for diagnostic, nav_path in items:
        if nav_path not in groups:
            groups[nav_path] = []
            order.append(nav_path)
        groups[nav_path].append((diagnostic, nav_path))

    merged: list[tuple[ValidatorDiagnostic, tuple[str, ...]]] = []
    for nav_path in order:
        group = groups[nav_path]
        kept = merge_union_pair(tuple(diagnostic for diagnostic, _ in group))
        kept_ids = {id(diagnostic) for diagnostic in kept}
        merged.extend(pair for pair in group if id(pair[0]) in kept_ids)
    return tuple(merged)
