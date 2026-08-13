"""Serialise a BPX document back to bytes (roundtrip and format conversion).

Editing is not yet supported, so export faithfully re-serialises the raw
dictionary that was loaded. Choosing a different format performs a JSON
<-> YAML conversion.
"""

from __future__ import annotations

import json

import yaml


def to_json(raw: dict, indent: int = 2) -> bytes:
    # Deliberately permissive: json.dumps emits bare NaN/Infinity/-Infinity
    # tokens for non-finite floats. That is valid for Python's own json
    # module and for bpx's loader (both round-trip it), but not RFC 8259
    # JSON, so a strict external consumer would reject the file. Blocking
    # the save here would be stricter than the bpx validator itself, which
    # is the one thing this app must never be -- see "Validator fidelity"
    # in the project guide. Kept permissive on purpose.
    return json.dumps(raw, indent=indent, ensure_ascii=False).encode("utf-8")


def to_yaml(raw: dict) -> bytes:
    return yaml.safe_dump(raw, sort_keys=False, allow_unicode=True).encode("utf-8")


def to_bytes(raw: dict, fmt: str) -> bytes:
    """Serialise ``raw`` to ``"json"`` or ``"yaml"`` (defaults to JSON)."""
    return to_yaml(raw) if fmt == "yaml" else to_json(raw)
