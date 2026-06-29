"""Create new incomplete BPX documents (frontend-agnostic).

A new document is an *incomplete structural scaffold*: real identity fields
(BPX version, model, title), the required object sections present but empty, and
**no invented scientific values**. Validation then guides completion, so the app
never produces a misleading-but-valid file.

This module owns only the "new blank document" workflow. New-from-reference,
imports (PyBaMM/LIIONDB) and clone are separate services with their own
provenance; they must not be folded in here.
"""

from __future__ import annotations

from . import bpx_gateway, structure

SUPPORTED_MODELS: tuple[str, ...] = ("SPM", "SPMe", "DFN", "Partial")


def create(model: str, title: str = "") -> dict:
    """Return an incomplete structural scaffold for ``model``.

    Required object sections are present as empty dicts; required fields are
    intentionally absent so the document validates as incomplete and the user is
    guided to fill them in.
    """
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model: {model!r}")
    raw: dict = {
        "Header": {
            "BPX": bpx_gateway.BPX_VERSION,
            "Title": title or f"New {model} (incomplete)",
            "Model": model,
        }
    }
    for path in structure.required_sections(model):
        _ensure_section(raw, path)
    return raw


def _ensure_section(raw: dict, path: tuple[str, ...]) -> None:
    node = raw
    for key in path:
        node = node.setdefault(key, {})
