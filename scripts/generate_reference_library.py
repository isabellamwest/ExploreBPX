"""Generate the bundled PyBaMM-derived BPX reference library.

Converts a curated list of PyBaMM's published lithium-ion parameter sets into
BPX documents under ``app/data/example_documents/pybamm/``, for use as
read-only *reference artifacts* (comparison and plotting) inside Explore_BPX.
See ``docs/future.md`` ("Bundled PyBaMM parameter sets as a reference
library") for the accepted constraints this tool implements:

* **Offline, dev-time only.** This script imports ``pybamm``; the application
  never does. The app loads the emitted files as ordinary data through
  ``core``. (The ``import bpx`` here is likewise fine: the gateway rule in
  the project guide scopes to ``app/``, and this tool *is* the validator check.)
* **Reference artifact, not simulation-grade.** Only the subset of parameters
  with a BPX home is carried over; each emitted Description says so.
* **DFN-shaped lithium-ion sets only.** MSMR and lead-acid sets do not map.

What is derived rather than copied (the lossy conversions, recorded in each
file's Description):

* Analytic functions (OCPs, electrolyte properties, sto-dependent
  diffusivities) are sampled onto interpolated tables at the set's reference
  temperature.
* Temperature dependence is reduced to Arrhenius activation energies
  extracted from a two-temperature ratio; a function whose T-dependence is
  not pure Arrhenius keeps only its best Arrhenius fit at T_ref (BPX cannot
  represent more).
* Min/max stoichiometries are computed with PyBaMM's eSOH utilities (they
  are not stored in the sets).
* The BPX reaction rate constant is reconstructed by inverting the exact
  normalisation PyBaMM's own BPX reader applies
  (``k_pybamm = k_bpx * F / (c_max * sqrt(c_e0))``), so the round-trip is
  algebraically consistent by construction.
* A concentration-dependent cation transference number collapses to its
  value at the initial electrolyte concentration.

Every emitted document is validated with ``bpx.parse_bpx_obj`` (the same
version the app pins) and round-tripped back into PyBaMM via
``ParameterValues.create_from_bpx``; the fidelity report (max OCP deviation,
electrolyte property error) is printed. A set that fails either check is
skipped loudly, never written half-converted.

Output is deterministic: fixed sampling grids, floats rounded to
``SIG_DIGITS`` significant digits, ``json.dump`` with ``indent=1`` and no
``sort_keys``, LF newlines, no timestamps.

Run with a python that has BOTH pybamm and bpx (matching the app's pin)
installed -- neither is an app dependency, e.g.:

    uv venv /tmp/pybamm-venv --python 3.12
    uv pip install -p /tmp/pybamm-venv/bin/python pybamm "bpx==1.1.1"
    /tmp/pybamm-venv/bin/python scripts/generate_reference_library.py
"""

from __future__ import annotations

import copy
import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import bpx
import numpy as np
import pybamm

OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "example_documents" / "pybamm"

#: Emitted BPX standard version (string form; the float form is deprecated).
BPX_STANDARD_VERSION = "1.1.0"

#: Significant digits for every float written (matches the example-library
#: builder's leanness policy; ~1e-6 relative, far below conversion error).
SIG_DIGITS = 6

#: Stoichiometry sampling grid for sto-dependent diffusivities (smooth
#: enough for a uniform grid). Clear of 0/1 where analytic fits typically
#: diverge (log terms).
STO_GRID = np.linspace(0.005, 0.995, 199)

#: OCPs get *adaptive* sampling instead: graphite staging steps and LFP
#: plateau knees put mV-scale linear-interpolation error on any affordable
#: uniform grid. Refinement targets this interpolation tolerance [V] and is
#: capped at this many points per table.
OCP_TOL_V = 5e-4
OCP_MAX_POINTS = 900

#: Electrolyte concentration sampling grid [mol.m-3] -- the validity window
#: of the usual conductivity/diffusivity correlations (e.g. Nyman 2008).
CE_GRID = np.linspace(200.0, 2000.0, 37)

#: Second temperature for Arrhenius extraction (paired with each set's own
#: reference temperature).
DELTA_T = 20.0

#: Activation energies below this [J.mol-1] are treated as "no temperature
#: dependence" and omitted (numerical noise from flat ratios).
EA_FLOOR = 10.0

FARADAY = 96485.33212


@dataclass(frozen=True)
class SetMeta:
    """Hand-curated identity for one PyBaMM parameter set."""

    pybamm_name: str  # pybamm.ParameterValues(<name>)
    slug: str  # output file stem
    cell: str  # short cell description for the Title
    citation: str  # the parameterisation's own paper


SETS: tuple[SetMeta, ...] = (
    SetMeta(
        pybamm_name="Chen2020",
        slug="chen2020",
        cell="LG M50 21700 (graphite | NMC811)",
        citation=(
            "Chen et al. (2020), J. Electrochem. Soc. 167 080534, "
            "doi:10.1149/1945-7111/ab9050"
        ),
    ),
    SetMeta(
        pybamm_name="Marquis2019",
        slug="marquis2019",
        cell="Kokam SLPB78205130H pouch cell",
        citation=(
            "Marquis et al. (2019), J. Electrochem. Soc. 166 A3693, "
            "doi:10.1149/2.0341915jes"
        ),
    ),
    SetMeta(
        pybamm_name="Prada2013",
        slug="prada2013",
        cell="A123 26650 (graphite | LFP)",
        citation=(
            "Prada et al. (2013), J. Electrochem. Soc. 160 A616, "
            "doi:10.1149/2.053304jes"
        ),
    ),
    SetMeta(
        pybamm_name="Ai2020",
        slug="ai2020",
        cell="Enertech pouch cell (graphite | LCO)",
        citation=(
            "Ai et al. (2020), J. Electrochem. Soc. 167 013512, "
            "doi:10.1149/2.0122001JES"
        ),
    ),
    SetMeta(
        pybamm_name="Mohtat2020",
        slug="mohtat2020",
        cell="NMC111 | graphite pouch cell",
        citation=(
            "Mohtat et al. (2020), J. Electrochem. Soc. 167 110561, "
            "doi:10.1149/1945-7111/aba5d1"
        ),
    ),
)


class SkipSet(Exception):
    """This set cannot be converted faithfully; skip it with a reason."""


# --- Evaluation helpers ------------------------------------------------------


def _evaluate(value, *args) -> float:
    """Evaluate a pybamm parameter entry to a plain float.

    Entries come in three shapes: a number, a callable returning a number or
    a pybamm expression, or a data interpolant tuple (handled separately by
    :func:`_as_data_table` -- reaching one here is a conversion error).
    """
    if isinstance(value, tuple):
        raise SkipSet("unexpected data-interpolant where a function was expected")
    if callable(value):
        out = value(*args)
        if isinstance(out, pybamm.Symbol):
            out = out.evaluate()  # interpolants return (1, 1) arrays
        arr = np.asarray(out)
        if arr.size != 1:
            raise SkipSet(f"expected a scalar evaluation, got shape {arr.shape}")
        return float(arr.item())
    return float(value)


def _as_data_table(value) -> tuple[list[float], list[float]] | None:
    """The ``(x, y)`` arrays of a pybamm data-interpolant entry, else None."""
    if not isinstance(value, tuple):
        return None
    name, data = value
    x, y = (data[0][0], data[1]) if isinstance(data[0], list) else data
    return list(np.asarray(x, dtype=float)), list(np.asarray(y, dtype=float))


def _table(x: np.ndarray, y: list[float]) -> dict:
    """BPX interpolated-table dict form."""
    return {"x": list(x), "y": list(y)}


def _round_floats(node, digits: int = SIG_DIGITS):
    """Recursively round every float to *digits* significant digits."""
    if isinstance(node, dict):
        return {key: _round_floats(child, digits) for key, child in node.items()}
    if isinstance(node, list):
        return [_round_floats(child, digits) for child in node]
    if isinstance(node, float):
        if node == 0 or not math.isfinite(node):
            return node
        return round(node, digits - 1 - math.floor(math.log10(abs(node))))
    return node


def _activation_energy(fn_of_t, t_ref: float) -> float | None:
    """Arrhenius activation energy from a two-temperature ratio, or None.

    ``fn_of_t`` maps a temperature to the property's value; the extracted Ea
    reproduces exactly the ``exp(Ea/R * (1/T_ref - 1/T))`` factor PyBaMM's
    BPX reader will re-apply, so a purely-Arrhenius source round-trips
    losslessly.
    """
    t_2 = t_ref + DELTA_T
    v_ref, v_2 = fn_of_t(t_ref), fn_of_t(t_2)
    if v_ref <= 0 or v_2 <= 0:
        raise SkipSet("non-positive property value during Arrhenius extraction")
    r_gas = 8.314462618
    ea = r_gas * math.log(v_2 / v_ref) / (1.0 / t_ref - 1.0 / t_2)
    return ea if abs(ea) > EA_FLOOR else None


# --- Section builders --------------------------------------------------------


class ConversionLog:
    """What the converter actually did to one set, so the emitted Description
    states only conversions that happened rather than a generic pipeline
    summary."""

    def __init__(self) -> None:
        self.sampled_sto: list[str] = []  # sampled over stoichiometry only
        self.sampled_at_t: list[str] = []  # sampled with temperature pinned
        self.copied: list[str] = []  # measured data carried over unchanged
        self.arrhenius: list[str] = []  # T-dependence reduced to an Ea
        self.extra: list[str] = []  # one-off conversion clauses


def _label(key: str) -> str:
    """A pybamm entry name as description prose (unit suffix dropped)."""
    name = key.split(" [")[0]
    return name[0].lower() + name[1:]


def _sampled_or_scalar(
    pv, key: str, t_ref: float, log: ConversionLog
) -> tuple[object, float | None]:
    """A sto-dependent property as (scalar | table, activation energy).

    Handles the three source shapes: plain number, callable of ``(sto, T)``,
    and measured-data interpolant. Activation energy is extracted at
    mid-stoichiometry for callables and is None for data entries.
    """
    value = pv[key]
    data = _as_data_table(value)
    if data is not None:
        x, y = data
        log.copied.append(_label(key))
        return {"x": x, "y": y}, None
    if callable(value):
        ea = _activation_energy(lambda t: _evaluate(value, 0.5, t), t_ref)
        log.sampled_at_t.append(_label(key))
        if ea is not None:
            log.arrhenius.append(_label(key))
        y = [_evaluate(value, s, t_ref) for s in STO_GRID]
        return _table(STO_GRID, y), ea
    return float(value), None


def _adaptive_grid(
    fn, lo: float, hi: float, tol: float, start: int = 41, max_points: int = OCP_MAX_POINTS
) -> tuple[list[float], list[float]]:
    """Sample ``fn`` so linear interpolation between nodes stays within
    *tol*: repeatedly evaluate every interval's midpoint and keep the ones
    the current polyline misses by more than *tol* as new nodes.
    Deterministic (pure arithmetic, fixed rounds) and capped at
    *max_points* -- hitting the cap is reported by the round-trip fidelity
    gate rather than silently accepted."""
    import bisect

    xs = list(np.linspace(lo, hi, start))
    ys = [fn(x) for x in xs]
    for _ in range(12):
        inserts = []
        for i in range(len(xs) - 1):
            x_mid = 0.5 * (xs[i] + xs[i + 1])
            y_mid = fn(x_mid)
            if abs(y_mid - 0.5 * (ys[i] + ys[i + 1])) > tol:
                inserts.append((x_mid, y_mid))
        if not inserts:
            break
        for x_mid, y_mid in inserts[: max(0, max_points - len(xs))]:
            index = bisect.bisect(xs, x_mid)
            xs.insert(index, x_mid)
            ys.insert(index, y_mid)
        if len(xs) >= max_points:
            break
    return xs, ys


def _ocp_table(pv, key: str, sto_min: float, sto_max: float, log: ConversionLog) -> dict:
    """An OCP as an interpolated table over stoichiometry (OCPs take sto
    only; entropic T-dependence lives in a separate coefficient carried
    elsewhere).

    The sampled range is the usual near-full [0.005, 0.995] *widened* to the
    electrode's own eSOH stoichiometry window when that dips lower/higher
    (e.g. an LFP positive at 0.0038): the operating window must lie on real
    nodes, never on edge extrapolation. The fixed floor is kept for
    everything else because analytic fits typically diverge at exactly 0/1.
    """
    value = pv[key]
    data = _as_data_table(value)
    if data is not None:
        x, y = data
        log.copied.append(_label(key))
        return {"x": x, "y": y}
    lo, hi = min(0.005, sto_min), max(0.995, sto_max)
    xs, ys = _adaptive_grid(lambda s: _evaluate(value, s), lo, hi, OCP_TOL_V)
    log.sampled_sto.append(_label(key))
    return {"x": xs, "y": ys}


def _electrode(
    pv, prefix: str, sto_min: float, sto_max: float, t_ref: float, c_e0: float, log: ConversionLog
) -> dict:
    """One electrode's BPX section from pybamm's ``<prefix> ...`` entries."""
    particle = "Negative particle" if prefix == "Negative electrode" else "Positive particle"
    c_max = _evaluate(pv[f"Maximum concentration in {prefix.lower()} [mol.m-3]"])
    radius = _evaluate(pv[f"{particle} radius [m]"])
    eps_am = _evaluate(pv[f"{prefix} active material volume fraction"])
    porosity = _evaluate(pv[f"{prefix} porosity"])
    bruggeman = _evaluate(pv[f"{prefix} Bruggeman coefficient (electrolyte)"])

    diffusivity, ea_d = _sampled_or_scalar(pv, f"{particle} diffusivity [m2.s-1]", t_ref, log)

    # Invert the exact normalisation pybamm's BPX reader applies:
    # reader: k_pybamm = k_bpx * F / (c_max * sqrt(c_e0)); here the source
    # j0(c_e, c_s, c_max, T) is evaluated at a reference point to recover
    # k_pybamm, then mapped back. Any (c_e, c_s) point works for a
    # Butler-Volmer-shaped j0; mid-stoichiometry is numerically safest.
    j0_fn = pv[f"{prefix} exchange-current density [A.m-2]"]
    c_s_ref = c_max / 2.0
    j0_shape = c_e0**0.5 * c_s_ref**0.5 * (c_max - c_s_ref) ** 0.5

    def _j0(t: float) -> float:
        return _evaluate(j0_fn, c_e0, c_s_ref, c_max, t)

    k_pybamm = _j0(t_ref) / j0_shape
    k_bpx = k_pybamm * c_max * c_e0**0.5 / FARADAY
    ea_k = _activation_energy(_j0, t_ref)
    if ea_k is not None:
        log.arrhenius.append(f"{prefix.lower()} reaction rate constant")

    section = {
        "Particle radius [m]": radius,
        "Thickness [m]": _evaluate(pv[f"{prefix} thickness [m]"]),
        "Diffusivity [m2.s-1]": diffusivity,
        "OCP [V]": _ocp_table(pv, f"{prefix} OCP [V]", sto_min, sto_max, log),
        "Conductivity [S.m-1]": _evaluate(pv[f"{prefix} conductivity [S.m-1]"]),
        "Surface area per unit volume [m-1]": 3.0 * eps_am / radius,
        "Porosity": porosity,
        "Transport efficiency": porosity**bruggeman,
        "Reaction rate constant [mol.m-2.s-1]": k_bpx,
        "Minimum stoichiometry": sto_min,
        "Maximum stoichiometry": sto_max,
        "Maximum concentration [mol.m-3]": c_max,
    }
    if ea_d is not None:
        section["Diffusivity activation energy [J.mol-1]"] = ea_d
    if ea_k is not None:
        section["Reaction rate constant activation energy [J.mol-1]"] = ea_k

    # Optional in BPX, but PyBaMM's own eSOH machinery needs it when reading
    # the document back with an initial state-of-charge, so carry it over
    # (a scalar, or a table sampled over stoichiometry -- entropic change
    # functions take sto only).
    entropic = pv[f"{prefix} OCP entropic change [V.K-1]"]
    if callable(entropic):
        log.sampled_sto.append(_label(f"{prefix} OCP entropic change [V.K-1]"))
        section["Entropic change coefficient [V.K-1]"] = _table(
            STO_GRID, [_evaluate(entropic, s) for s in STO_GRID]
        )
    else:
        section["Entropic change coefficient [V.K-1]"] = float(entropic)
    return section


def _electrolyte(pv, t_ref: float, c_e0: float, log: ConversionLog) -> dict:
    """The electrolyte's BPX section; properties sampled over ``CE_GRID``."""
    t_plus = pv["Cation transference number"]
    conductivity_fn = pv["Electrolyte conductivity [S.m-1]"]
    diffusivity_fn = pv["Electrolyte diffusivity [m2.s-1]"]

    if callable(t_plus):
        log.extra.append(
            "the concentration-dependent cation transference number is collapsed "
            "to its value at the initial electrolyte concentration"
        )
    section: dict = {
        "Cation transference number": (
            _evaluate(t_plus, c_e0, t_ref) if callable(t_plus) else float(t_plus)
        ),
    }
    for name, alias, fn in (
        ("Electrolyte conductivity [S.m-1]", "Conductivity [S.m-1]", conductivity_fn),
        ("Electrolyte diffusivity [m2.s-1]", "Diffusivity [m2.s-1]", diffusivity_fn),
    ):
        if callable(fn):
            log.sampled_at_t.append(_label(name))
            section[alias] = _table(CE_GRID, [_evaluate(fn, c, t_ref) for c in CE_GRID])
            ea = _activation_energy(lambda t: _evaluate(fn, c_e0, t), t_ref)
            if ea is not None:
                log.arrhenius.append(_label(name))
                section[alias.split(" [")[0] + " activation energy [J.mol-1]"] = ea
        else:
            section[alias] = float(fn)
    return section


def _description(meta: SetMeta, t_ref: float, log: ConversionLog) -> str:
    """The Header Description, assembled from what the conversion actually
    did to *this* set (via ``log``) plus the steps every conversion performs.
    Every clause is evidence, not boilerplate."""
    conversions = []
    if log.sampled_sto:
        conversions.append(
            "analytic functions sampled onto interpolated tables over "
            "stoichiometry: " + ", ".join(log.sampled_sto)
        )
    if log.sampled_at_t:
        conversions.append(
            f"analytic functions sampled onto interpolated tables at {t_ref} K: "
            + ", ".join(log.sampled_at_t)
        )
    if log.arrhenius:
        conversions.append(
            "temperature dependence reduced to a best-fit Arrhenius activation "
            "energy for " + ", ".join(log.arrhenius)
        )
    conversions.extend(log.extra)
    applied = (
        " Conversions applied to this set: " + "; ".join(conversions) + "."
        if conversions
        else ""
    )
    carried = (
        " Measured data tables carried over unchanged: " + ", ".join(log.copied) + "."
        if log.copied
        else ""
    )
    return (
        f"Reference artifact converted from PyBaMM's {meta.pybamm_name} parameter set "
        f"({meta.citation}). Not simulation-grade: only parameters with a BPX home are "
        f"carried over; min/max stoichiometries are computed with PyBaMM's eSOH "
        f"utilities; reaction rate constants are reconstructed from the "
        f"exchange-current densities; degradation, current-collector and per-component "
        f"thermal parameters are omitted.{applied}{carried} Generated offline by "
        f"scripts/generate_reference_library.py (PyBaMM {pybamm.__version__})."
    )


def convert(meta: SetMeta) -> dict:
    """One PyBaMM parameter set as a BPX (DFN) document dict."""
    pv = pybamm.ParameterValues(meta.pybamm_name)
    t_ref = _evaluate(pv["Reference temperature [K]"])
    c_e0 = _evaluate(pv["Initial concentration in electrolyte [mol.m-3]"])

    x_0, x_100, y_100, y_0 = pybamm.lithium_ion.get_min_max_stoichiometries(pv)
    if not (x_0 < x_100 and y_100 < y_0):
        raise SkipSet("eSOH stoichiometry limits came back inverted")

    area = _evaluate(pv["Electrode width [m]"]) * _evaluate(pv["Electrode height [m]"])
    cell = {
        "Electrode area [m2]": area,
        "Number of electrode pairs connected in parallel to make a cell": int(
            _evaluate(pv["Number of electrodes connected in parallel to make a cell"])
        ),
        "Lower voltage cut-off [V]": _evaluate(pv["Lower voltage cut-off [V]"]),
        "Upper voltage cut-off [V]": _evaluate(pv["Upper voltage cut-off [V]"]),
        "Nominal cell capacity [A.h]": _evaluate(pv["Nominal cell capacity [A.h]"]),
        "Reference temperature [K]": t_ref,
    }
    for bpx_alias, pybamm_name in (
        ("External surface area [m2]", "Cell cooling surface area [m2]"),
        ("Volume [m3]", "Cell volume [m3]"),
    ):
        if pybamm_name in pv:
            cell[bpx_alias] = _evaluate(pv[pybamm_name])

    # PyBaMM's BPX reader recovers Bruggeman as log(transport efficiency) /
    # log(porosity), which is undefined at a porosity of exactly 1 (e.g.
    # Marquis2019's idealised separator) -- such a set cannot round-trip, so
    # it is skipped rather than shipped with nudged data.
    for domain in ("Negative electrode", "Positive electrode", "Separator"):
        if _evaluate(pv[f"{domain} porosity"]) >= 1.0:
            raise SkipSet(
                f"{domain} porosity is 1.0: PyBaMM's BPX reader cannot "
                "recover a Bruggeman coefficient from it (log(1) division)"
            )

    separator = {
        "Thickness [m]": _evaluate(pv["Separator thickness [m]"]),
        "Porosity": _evaluate(pv["Separator porosity"]),
        "Transport efficiency": _evaluate(pv["Separator porosity"])
        ** _evaluate(pv["Separator Bruggeman coefficient (electrolyte)"]),
    }

    # Sections are built before the Header so the conversion log is complete
    # by the time the Description is written from it.
    log = ConversionLog()
    electrolyte = _electrolyte(pv, t_ref, c_e0, log)
    negative = _electrode(pv, "Negative electrode", x_0, x_100, t_ref, c_e0, log)
    positive = _electrode(pv, "Positive electrode", y_100, y_0, t_ref, c_e0, log)

    return {
        "Header": {
            "BPX": BPX_STANDARD_VERSION,
            "Model": "DFN",
            "Title": f"{meta.pybamm_name} — {meta.cell} — PyBaMM reference",
            "Description": _description(meta, t_ref, log),
            "References": meta.citation,
        },
        "Parameterisation": {
            "Cell": cell,
            "Electrolyte": electrolyte,
            "Negative electrode": negative,
            "Positive electrode": positive,
            "Separator": separator,
        },
        "State": {
            "Initial conditions": {
                "Initial temperature [K]": t_ref,
                "Initial state-of-charge": 1.0,
                "Initial electrolyte concentration [mol.m-3]": c_e0,
            }
        },
    }


# --- Verification ------------------------------------------------------------


def _verify_bpx_valid(doc: dict) -> list[str]:
    """Parse with the official validator; returns warning texts, raises on
    invalid."""
    import warnings as _warnings

    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        bpx.parse_bpx_obj(copy.deepcopy(doc))
    return [str(w.message) for w in caught]


def _verify_round_trip(meta: SetMeta, doc: dict) -> dict[str, float]:
    """Load the emitted document back through PyBaMM's own BPX reader and
    measure fidelity against the source set. Returns the error report."""
    pv_src = pybamm.ParameterValues(meta.pybamm_name)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(doc, handle)
        path = handle.name
    pv_rt = pybamm.ParameterValues.create_from_bpx(path)
    t_ref = _evaluate(pv_src["Reference temperature [K]"])

    report: dict[str, float] = {}
    for prefix, lo, hi in (
        ("Negative electrode", doc["Parameterisation"]["Negative electrode"], None),
        ("Positive electrode", doc["Parameterisation"]["Positive electrode"], None),
    ):
        sto = np.linspace(lo["Minimum stoichiometry"], lo["Maximum stoichiometry"], 501)
        src = np.array([_evaluate(pv_src[f"{prefix} OCP [V]"], s) for s in sto])
        rt = np.array([_evaluate(pv_rt[f"{prefix} OCP [V]"], s) for s in sto])
        report[f"{prefix} OCP max dev [V]"] = float(np.max(np.abs(src - rt)))

    c_e0 = _evaluate(pv_src["Initial concentration in electrolyte [mol.m-3]"])
    for name in ("Electrolyte conductivity [S.m-1]", "Electrolyte diffusivity [m2.s-1]"):
        src_fn, rt_fn = pv_src[name], pv_rt[name]
        grid = CE_GRID[1:-1]
        src = np.array([_evaluate(src_fn, c, t_ref) for c in grid])
        rt = np.array([_evaluate(rt_fn, c, t_ref) for c in grid])
        report[f"{name} max rel err"] = float(np.max(np.abs(rt - src) / np.abs(src)))

    for prefix in ("Negative electrode", "Positive electrode"):
        c_max = _evaluate(pv_src[f"Maximum concentration in {prefix.lower()} [mol.m-3]"])
        c_s = c_max / 2.0
        src = _evaluate(pv_src[f"{prefix} exchange-current density [A.m-2]"], c_e0, c_s, c_max, t_ref)
        rt = _evaluate(pv_rt[f"{prefix} exchange-current density [A.m-2]"], c_e0, c_s, c_max, t_ref)
        report[f"{prefix} j0 rel err"] = abs(rt - src) / abs(src)
    return report


TOLERANCES = {
    "OCP max dev [V]": 2e-3,
    "max rel err": 2e-2,
    "j0 rel err": 1e-3,
}


def _check_report(report: dict[str, float]) -> list[str]:
    failures = []
    for key, value in report.items():
        tolerance = next(t for suffix, t in TOLERANCES.items() if key.endswith(suffix))
        if value > tolerance:
            failures.append(f"{key} = {value:.3e} exceeds {tolerance:.0e}")
    return failures


# --- Main --------------------------------------------------------------------


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []
    for meta in SETS:
        try:
            doc = _round_floats(convert(meta))
            bpx_warnings = _verify_bpx_valid(doc)
            report = _verify_round_trip(meta, doc)
            failures = _check_report(report)
            if failures:
                raise SkipSet("round-trip fidelity: " + "; ".join(failures))
        except SkipSet as reason:
            skipped.append((meta.pybamm_name, str(reason)))
            print(f"SKIPPED {meta.pybamm_name}: {reason}")
            continue
        except Exception as exc:  # noqa: BLE001 - report and move on, never half-write
            skipped.append((meta.pybamm_name, f"{type(exc).__name__}: {exc}"))
            print(f"SKIPPED {meta.pybamm_name}: {type(exc).__name__}: {exc}")
            continue

        path = OUT_DIR / f"{meta.slug}.json"
        with path.open("w", newline="\n") as handle:
            json.dump(doc, handle, indent=1)
            handle.write("\n")
        written.append(path.name)
        print(f"WROTE {path.name}  (bpx: VALID, {len(bpx_warnings)} warnings)")
        for warning in bpx_warnings:
            print(f"    bpx warning: {warning}")
        for key, value in report.items():
            print(f"    {key}: {value:.3e}")

    print(f"\n{len(written)} written, {len(skipped)} skipped.")
    return 0 if written and not any("Chen2020" in name for name, _ in skipped) else 1


if __name__ == "__main__":
    raise SystemExit(main())
