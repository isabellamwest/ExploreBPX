# Source

Four BPX reference documents converted from [PyBaMM](https://pybamm.org)'s
published lithium-ion parameter sets by `scripts/generate_reference_library.py`
(PyBaMM 26.7.1.0), offline — the application never imports PyBaMM. Each file's
own `Header.Description` records the conversion caveats; in short, these are
**reference artifacts for comparison and plotting, not simulation-grade
parameter sets**: only parameters with a BPX home are carried over, analytic
functions are sampled as interpolated tables at the reference temperature,
temperature dependence is reduced to Arrhenius activation energies, min/max
stoichiometries are computed with PyBaMM's eSOH utilities, and the reaction
rate constant is reconstructed from the exchange-current density.

Every file passes `bpx.parse_bpx_obj` at the version the app pins and
round-trips into PyBaMM via `ParameterValues.create_from_bpx` within the
fidelity gates printed by the generator (max OCP deviation < 1 mV; electrolyte
property and exchange-current errors at the ppm level).

The underlying parameterisations are published in:

* `chen2020.json` — Chen et al. (2020), *J. Electrochem. Soc.* **167** 080534,
  doi:10.1149/1945-7111/ab9050 (LG M50 21700, graphite | NMC811).
* `prada2013.json` — Prada et al. (2013), *J. Electrochem. Soc.* **160** A616,
  doi:10.1149/2.053304jes (A123 26650, graphite | LFP).
* `ai2020.json` — Ai et al. (2020), *J. Electrochem. Soc.* **167** 013512,
  doi:10.1149/2.0122001JES (Enertech pouch cell, graphite | LCO).
* `mohtat2020.json` — Mohtat et al. (2020), *J. Electrochem. Soc.* **167**
  110561, doi:10.1149/1945-7111/aba5d1 (NMC532 | graphite pouch cell).

PyBaMM's Marquis2019 set is deliberately absent: its idealised separator
porosity of 1.0 cannot round-trip through PyBaMM's own BPX reader (the
Bruggeman coefficient is recovered as `log(transport efficiency)/log(porosity)`,
undefined at 1), so no faithful BPX rendering of it exists.

# License

PyBaMM and its bundled parameter sets are distributed under the
**BSD 3-Clause License** (https://github.com/pybamm-team/PyBaMM/blob/develop/LICENSE.txt).
The parameter values themselves originate in the publications cited above.
