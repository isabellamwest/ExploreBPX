# Source

Two BPX parameterisations by About:Energy Limited (aboutenergy.io), December 2022,
published in their public parameterisation repository:
https://github.com/About-Energy-OpenSource/About-Energy-BPX-Parameterisation

Pinned to commit `8efd45a7495ad8d3a4d72b547e657322a4baabd2` (branch `main`).

* `nmc_pouch_cell.json` — per its own `Header`: "Parameterisation example of an
  NMC111|graphite 12.5 Ah pouch cell". The **base document** is not the file from the
  About:Energy repo (which uses the legacy BPX 0.1 shape) but the same parameterisation
  migrated to modern BPX (BPX 1.0 header, proper `State` section), as published in the
  pybamm-data v1.0.2 release:
  https://github.com/pybamm-team/pybamm-data/releases/download/v1.0.2/nmc_pouch_cell_BPX.json
* `lfp_18650_cell.json` — base document is the About:Energy repo's
  `LFP/lfp_18650_cell_BPX.json` at the pinned commit, per its own `Header`:
  "Parameterisation example of an LFP|graphite 2 Ah cylindrical 18650 cell.
  Parameterisation by About:Energy Limited (aboutenergy.io), December 2022, based on
  cell cycling data, and electrode data gathered after cell teardown." It remains in
  the legacy BPX 0.1 shape it was published in; the `bpx` package auto-converts it on
  load (with a conversion warning, surfaced faithfully by the app).

Both cite Nyman et al. 2008 (electrolyte properties) and O'Regan et al. 2022
(negative electrode entropic coefficients); positive electrode entropic coefficients
from Viswanathan et al. 2010 (NMC) and Gerver and Meyers 2011 (LFP).

# License

The About:Energy repository is licensed **CC BY-SA 4.0** (Creative Commons
Attribution-ShareAlike 4.0 International); the full legal text is bundled alongside as
`LICENSE-CC-BY-SA-4.0.txt`. The bundled files are *modified* copies (see below) and are
distributed under the same license, as ShareAlike requires.

# Modifications

Each document's `Validation` section was **rebuilt** from the repo's full-resolution
25 °C validation CSVs (`{NMC,LFP}/data/validation/*_25degC_*.csv`, columns
`Time [s], I[A], U[V]`), replacing whatever the base document carried:

* Five runs per chemistry: "C/20 discharge", "C/2 discharge", "1C discharge",
  "2C discharge", "Drive cycle".
* Each run downsampled to at most 1000 uniformly spaced samples (index
  `round(j * (n - 1) / 999)`), always keeping the first and last sample; runs already
  at or under 1000 points are untouched.
* All floats rounded to 6 significant digits to keep the bundled files lean.
* The CSVs carry no temperature column, so no `"Temperature [K]"` series is included.
* A short provenance note is appended to each document's `Header.Description`.

Parameter data was **not** modified. Sign convention and values are exactly as
upstream (the CSVs record discharge current as negative).

# Validity

Both bundled files load as *valid* through this app's own `bpx_gateway` pipeline under
`bpx` 1.1.1, with warnings only: the NMC file warns about its float-valued `BPX`
header field and an STO-limit/voltage-cut-off tolerance check (twice); the LFP file
carries the legacy-conversion warning described above.

# Regenerating

From the repo root:

    uv run python scripts/build_example_library.py

The script (`scripts/build_example_library.py`) pins all source URLs/SHAs as
constants, is deterministic (no timestamps, source key order preserved), and rewrites
both JSON files and the bundled license text.
