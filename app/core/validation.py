"""Validation issue model and normalisers (frontend-agnostic).

Converts BPX/Pydantic validation output into a stable, UI-neutral
``ValidationIssue`` representation keyed by an alias path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Trailing tokens Pydantic appends to a ``loc`` to indicate which member of a
# union failed (e.g. ``Union[float, int]``). They are not part of the data path.
_UNION_TAGS = frozenset(
    {
        "float",
        "int",
        "str",
        "bool",
        "number",
        "integer",
        "boolean",
        "string",
        "function-after",
        "function-before",
        "is-instance",
    }
)


class Severity(str, Enum):
    """Severity of a validation issue."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation problem, located by an alias path.

    ``path`` uses BPX aliases (e.g. ``("Cell", "Upper voltage cut-off [V]")``).
    It may be a partial path because Pydantic reports locations relative to the
    section being validated; navigation uses best-effort suffix matching.
    """

    path: tuple[str, ...]
    message: str
    severity: Severity = Severity.ERROR

    @property
    def path_str(self) -> str:
        return " → ".join(self.path) if self.path else "(document root)"


def _strip_union_tags(loc: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = list(loc)
    while cleaned and cleaned[-1] in _UNION_TAGS:
        cleaned.pop()
    return tuple(cleaned)


def issues_from_pydantic(errors: list[dict]) -> list[ValidationIssue]:
    """Normalise ``ValidationError.errors()`` into deduplicated issues.

    Union fields (e.g. ``float | int``) emit one error per union member at the
    same location; these are collapsed to a single issue.
    """
    issues: list[ValidationIssue] = []
    seen: set[tuple[str, ...]] = set()
    for error in errors:
        loc = tuple(str(part) for part in error.get("loc", ()))
        path = _strip_union_tags(loc)
        if path in seen:
            continue
        seen.add(path)
        issues.append(
            ValidationIssue(
                path=path,
                message=error.get("msg", "Invalid value"),
                severity=Severity.ERROR,
            )
        )
    return issues


def issue_from_message(
    message: object,
    severity: Severity = Severity.ERROR,
    path: tuple[str, ...] = (),
) -> ValidationIssue:
    """Build a single issue from a free-form message (non-Pydantic errors)."""
    return ValidationIssue(path=tuple(path), message=str(message), severity=severity)
