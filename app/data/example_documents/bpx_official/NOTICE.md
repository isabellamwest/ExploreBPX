# Source

These files are copied unmodified from the official BPX repository:
https://github.com/FaradayInstitution/BPX/tree/v1.1.0/examples

Pinned to git tag `v1.1.0` (commit `eb5da74588631ffee0e81f00746352a3f5ba5414`), matching the
`bpx` package version this app is built against. `BPX_LICENSE.txt` is that repository's
MIT `LICENSE.txt`, copied alongside for attribution.

Per each file's own `Header.Description`: parameterisation by About:Energy Limited
(aboutenergy.io), December 2022, citing Nyman et al. 2008 (electrolyte properties),
O'Regan et al. 2022 (negative electrode entropic coefficients), and Viswanathan et al.
2010 (positive electrode entropic coefficients).

## Why only these two files

The BPX repo ships five example files. Only these two contain a populated `Validation`
section (real Time/Current/Voltage/Temperature discharge curves) — the other three
(`lfp_18650_cell_BPX.json`, `nmc_pouch_cell_BPX_blended_electrode.json`,
`nmc_pouch_cell_BPX_user-defined_hysteresis.json`) are parameter-only test cases with no
experimental data, so they have nothing to contribute to a Validation-run comparison
feature and were not bundled.

## Known validity note

As of `v1.1.0`, both files fail validation under the `bpx` package of the same version —
confirmed by loading them through this app's own `bpx_gateway` pipeline, not assumed. Both
report the same two schema-migration errors: `Cell.Initial temperature [K]` /
`Ambient temperature [K]` have moved to `State.InitialConditions` / `State.ThermalState`,
and `Electrolyte.Initial concentration [mol.m-3]` has moved to
`State.InitialConditions.Initial electrolyte concentration [mol.m-3]`. This is a staleness
issue in the upstream repo's own examples, not something introduced by copying them here —
verified by diffing against the `main` branch, which is byte-identical.

Explore_BPX only reads the `Validation` section of these files (see
`app/core/example_library.py`) and never surfaces or claims validity for the rest of the
document, so this does not affect what the app actually shows.
