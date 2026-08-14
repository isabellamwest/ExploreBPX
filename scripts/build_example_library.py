"""Build the bundled About:Energy example library.

Downloads pinned upstream sources and regenerates
``app/data/example_documents/about_energy/``:

* ``nmc_pouch_cell.json`` -- base document is the BPX-1.0-migrated NMC pouch
  cell file published in the pybamm-data v1.0.2 release; its ``Validation``
  section is replaced with five runs rebuilt from About:Energy's
  full-resolution validation CSVs.
* ``lfp_18650_cell.json`` -- base document is About:Energy's LFP 18650 cell
  BPX file (legacy BPX 0.1 shape, left untouched); a ``Validation`` section
  built the same way is appended.
* ``LICENSE-CC-BY-SA-4.0.txt`` -- the full CC BY-SA 4.0 legal text.

Everything is pinned (commit SHA / release tag) and the output is
deterministic: no timestamps, source key order preserved, ``json.dump`` with
``indent=1`` and no ``sort_keys``, LF newlines.

Downsampling policy: a run longer than ``MAX_POINTS`` samples is reduced to
exactly ``MAX_POINTS`` uniformly spaced samples chosen by index
``round(j * (n - 1) / (MAX_POINTS - 1))`` -- the first and last samples are
always kept. Runs already at or under the limit are untouched. All floats are
rounded to ``SIG_DIGITS`` significant digits to keep the bundled files lean.

Run from the repo root:

    uv run python scripts/build_example_library.py
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

# --- Pinned sources ---------------------------------------------------------

#: About:Energy public parameterisation repo, pinned to a specific commit.
AE_REPO = "About-Energy-OpenSource/About-Energy-BPX-Parameterisation"
AE_COMMIT = "8efd45a7495ad8d3a4d72b547e657322a4baabd2"
AE_RAW = f"https://raw.githubusercontent.com/{AE_REPO}/{AE_COMMIT}"

#: The NMC pouch cell file migrated to modern BPX (proper ``State`` section),
#: from the pinned pybamm-data release.
PYBAMM_NMC_URL = "https://github.com/pybamm-team/pybamm-data/releases/download/v1.0.2/nmc_pouch_cell_BPX.json"

#: About:Energy's LFP BPX file at the pinned commit.
AE_LFP_URL = f"{AE_RAW}/LFP/lfp_18650_cell_BPX.json"

#: Full CC BY-SA 4.0 legal text (the repo's license).
CC_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/legalcode.txt"

#: Validation runs common to both chemistries: bundled run name -> the tag
#: used in the CSV filenames (``{CHEM}/data/validation/{CHEM}_25degC_{tag}.csv``).
RUNS: tuple[tuple[str, str], ...] = (
    ("C/20 discharge", "Co20"),
    ("C/2 discharge", "Co2"),
    ("1C discharge", "1C"),
    ("2C discharge", "2C"),
    ("Drive cycle", "DriveCycle"),
)

#: Exact column headers of the upstream validation CSVs.
CSV_COLUMNS = ("Time [s]", "I[A]", "U[V]")

MAX_POINTS = 1000
SIG_DIGITS = 6

PROVENANCE_NOTE = (
    "Validation runs rebuilt from About:Energy full-resolution validation data (downsampled), see NOTICE.md."
)

OUT_DIR = Path(__file__).resolve().parents[1] / "app" / "data" / "example_documents" / "about_energy"


# --- Helpers ----------------------------------------------------------------


def fetch(url: str) -> bytes:
    """Download *url* and return its body."""
    request = urllib.request.Request(url, headers={"User-Agent": "Explore_BPX-build-script"})  # noqa: S310
    with urllib.request.urlopen(request) as response:  # noqa: S310 - fixed https URLs from this script's own constants
        return response.read()


def read_validation_csv(url: str) -> tuple[list[float], list[float], list[float]]:
    """Parse an upstream validation CSV into (time, current, voltage) columns.

    The header is asserted verbatim so a silent upstream format change fails
    loudly instead of producing wrong data.
    """
    text = fetch(url).decode("utf-8-sig")
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    if tuple(rows[0]) != CSV_COLUMNS:
        raise ValueError(f"Unexpected CSV header {rows[0]!r} in {url}")
    time, current, voltage = [], [], []
    for row in rows[1:]:
        time.append(float(row[0]))
        current.append(float(row[1]))
        voltage.append(float(row[2]))
    return time, current, voltage


def downsample_indices(n: int) -> list[int]:
    """Uniformly spaced sample indices for a run of *n* points (see module
    docstring). Always includes ``0`` and ``n - 1``; never exceeds
    ``MAX_POINTS``."""
    if n <= MAX_POINTS:
        return list(range(n))
    raw = (round(j * (n - 1) / (MAX_POINTS - 1)) for j in range(MAX_POINTS))
    return list(dict.fromkeys(raw))  # dedupe rounding collisions, order kept


def round_sig(value: float) -> float:
    """Round to ``SIG_DIGITS`` significant digits."""
    return float(f"{value:.{SIG_DIGITS}g}")


def build_validation(chem: str) -> tuple[dict, list[tuple[str, int, int]]]:
    """Build the ``Validation`` section for *chem* (``"NMC"``/``"LFP"``).

    Returns the section plus per-run (name, points before, points after)
    stats for the provenance report.
    """
    section: dict = {}
    stats: list[tuple[str, int, int]] = []
    for run_name, tag in RUNS:
        url = f"{AE_RAW}/{chem}/data/validation/{chem}_25degC_{tag}.csv"
        time, current, voltage = read_validation_csv(url)
        indices = downsample_indices(len(time))
        section[run_name] = {
            # The upstream CSVs carry no temperature column, so no
            # "Temperature [K]" series is invented here.
            "Time [s]": [round_sig(time[i]) for i in indices],
            "Current [A]": [round_sig(current[i]) for i in indices],
            "Voltage [V]": [round_sig(voltage[i]) for i in indices],
        }
        stats.append((run_name, len(time), len(indices)))
    return section, stats


def build_document(base_url: str, chem: str) -> tuple[dict, list[tuple[str, int, int]]]:
    """Load the base BPX document and install the rebuilt ``Validation``.

    Source key order is preserved: an existing ``Validation`` is replaced in
    place; otherwise the section is appended last.
    """
    document = json.loads(fetch(base_url).decode("utf-8"))
    validation, stats = build_validation(chem)
    document["Validation"] = validation  # replaces in place, or appends last
    header = document["Header"]
    header["Description"] = f"{header['Description'].rstrip()} {PROVENANCE_NOTE}"
    return document, stats


def write_json(path: Path, document: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, indent=1)
        handle.write("\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for filename, base_url, chem in (
        ("nmc_pouch_cell.json", PYBAMM_NMC_URL, "NMC"),
        ("lfp_18650_cell.json", AE_LFP_URL, "LFP"),
    ):
        document, stats = build_document(base_url, chem)
        path = OUT_DIR / filename
        write_json(path, document)
        print(f"{path.name} ({path.stat().st_size:,} bytes)")
        for run_name, before, after in stats:
            print(f"  {run_name}: {before} -> {after} points")

    license_path = OUT_DIR / "LICENSE-CC-BY-SA-4.0.txt"
    license_path.write_bytes(fetch(CC_LICENSE_URL))
    print(f"{license_path.name} ({license_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
