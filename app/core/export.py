"""Serialise a BPX document back to bytes (roundtrip and format conversion).

Editing is not yet supported, so export faithfully re-serialises the raw
dictionary that was loaded. Choosing a different format performs a JSON
<-> YAML conversion.
"""

from __future__ import annotations

import json

import yaml


def to_json(raw: dict, indent: int = 2) -> bytes:
    return json.dumps(raw, indent=indent, ensure_ascii=False).encode("utf-8")


def to_yaml(raw: dict) -> bytes:
    return yaml.safe_dump(raw, sort_keys=False, allow_unicode=True).encode("utf-8")


def to_bytes(raw: dict, fmt: str) -> bytes:
    """Serialise ``raw`` to ``"json"`` or ``"yaml"`` (defaults to JSON)."""
    return to_yaml(raw) if fmt == "yaml" else to_json(raw)
