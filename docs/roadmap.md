# Roadmap

Explore_BPX is built incrementally. Every version is useful on its own; later
features build on the V1 foundation without requiring it to be rewritten.

**Project Schematic (goal)** - a standalone, dashboard-like app at the centre of the BPX ecosystem that makes BPX user-friendly. It connects parameter *sources* (experimental and modelling parameterisation, external BPX databases) to *simulators* (PyBOP, PyProBE), supports easier create/edit/visualise workflows, validates beyond syntax, and advances standardisation. V1 below is the read-only framework everything else bolts on to.  

## V1 — Read-only explorer (current)

The smallest genuinely useful version, and the framework every later feature extends from.

- Open JSON/YAML BPX files, including invalid ones.
- Navigate: Tree → Section → Parameter → Inspector.
- Read-only display of every parameter kind (scalar, integer, enum, function,
  table, section) with units and schema descriptions.
- Continuous validation: inline issues on parameters plus a Validation tab that
  links to the offending parameter.
- Export / round-trip as JSON or YAML.

**Excluded from V1:** editing, visualisation, JSON editing, file comparison,
templates, multi-file handling, and any duplication of BPX logic.

## V2 — Editing, creation and visualisation

Creation, editing and visualisation are at the heart of the GUI, so creation is a first-class goal.

- Edit scalars and enums first, then functions and tables.
- Create new BPX files via templates / scaffolds for SPM, SPMe, DFN and Partial
- Re-validate after edits (continuous).
- Visualise functions and interpolated tables (e.g. OCP plots) using
  `Function.to_python_function()`.
- Read-only raw JSON view.

## V3 - Validation beyond syntax, and ecosystem connections

- **Sanity Check** - plausibility validation that visually compares parameter values against known / typical cell parameters, distict from the existing schema / syntax check. This will require a reference dataset of cell parameters (design-tension note in [architecture.md](architecture.md))
- **External database import** - pull parameters from open-source BPX databases such as LIIONDB, and other BPX databases, as additional sources.
- **Simulator hand-off** - export / hand BPX off to simulators, with **PyBOP** and **PyProBE** as the first targets; framed under simulator compatibility and standardisation. 


## Future

- Compare two BPX files (parameter diff and overlaid plots).
- Multi-file library / data management.
- Standalone distribution and an alternative frontend (Pyside6 / web) reusing the 'core' and 'state' layers. 
- Further modelling-assistant features building on the simulator hand-off. 