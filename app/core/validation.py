"""Validator diagnostic model.

Provides lossless wrappers around the diagnostic objects produced by the BPX
validation pipeline.  Each concrete type preserves the original object exactly
as the pipeline returned it and exposes a stable typed interface over it.

Navigation, tree-matching and presentation are derived elsewhere; this module
only captures and exposes validator output.
"""

from __future__ import annotations

import warnings as _warnings
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
