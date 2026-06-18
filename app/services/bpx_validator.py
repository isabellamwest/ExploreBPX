import json

import yaml
from bpx.parsers import parse_bpx_obj


def _load_bpx_bytes(bpx_bytes: bytes, filename: str | None = None) -> dict:
    text = bpx_bytes.decode("utf-8")
    if filename and filename.lower().endswith((".yml", ".yaml")):
        parsed = yaml.safe_load(text)
    else:
        parsed = json.loads(text)

    if not isinstance(parsed, dict):
        raise ValueError("BPX file root must be a JSON/YAML object (dictionary).")

    return parsed


def validate_bpx_bytes(
    bpx_bytes: bytes,
    filename: str | None = None,
    v_tol: float = 0.001,
):
    bpx_data = _load_bpx_bytes(bpx_bytes, filename)
    return parse_bpx_obj(bpx_data, v_tol)
