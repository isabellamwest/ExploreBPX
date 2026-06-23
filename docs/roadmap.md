# Roadmap

Explore_BPX is built incrementally. Every version is useful on its own; later
features build on the V1 foundation without requiring it to be rewritten.

## V1 — Read-only explorer (current)

The smallest genuinely useful version.

- Open JSON/YAML BPX files, including invalid ones.
- Navigate: Tree → Section → Parameter → Inspector.
- Read-only display of every parameter kind (scalar, integer, enum, function,
  table, section) with units and schema descriptions.
- Continuous validation: inline issues on parameters plus a Validation tab that
  links to the offending parameter.
- Export / round-trip as JSON or YAML.

**Excluded from V1:** editing, visualisation, JSON editing, file comparison,
templates, multi-file handling, and any duplication of BPX logic.

## V2 — Editing and visualisation

- Edit scalars and enums first, then functions and tables.
- Re-validate after edits (continuous).
- Visualise functions and interpolated tables (e.g. OCP plots) using
  `Function.to_python_function()`.
- Read-only raw JSON view.

## Future

- Compare two BPX files (parameter diff and overlaid plots).
- Templates / scaffolds for SPM, SPMe, DFN and Partial.
- Multi-file library / data management.
- Alternative frontend (PySide6 / web) reusing the `core` and `state` layers.
- Modelling-assistant features (e.g. PyBaMM hand-off).