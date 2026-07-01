# Roadmap

Explore_BPX is built incrementally. Every version is useful on its own; later
features build on the Version 1 desktop foundation without requiring it to be
rewritten.

**Project Schematic (goal)** - a standalone, dashboard-like app at the centre of the BPX ecosystem that makes BPX user-friendly. It connects parameter *sources* (experimental and modelling parameterisation, external BPX databases) to *simulators* (PyBOP, PyProBE), supports easier create/edit/visualise workflows, validates beyond syntax, and advances standardisation.

## Version 1 — Qt explorer/editor foundation (current)

The smallest genuinely useful desktop app, and the framework every later feature extends from.

- Open JSON/YAML BPX files, including invalid ones.
- A fixed multi-pane shell: a left activity bar (Editor / Validation views), a
  three-pane Editor (Tree → object parameter list → Inspector), a top
  context/mode bar, a right Utility panel (Issues), and a bottom status bar.
- Typed per-kind display and editing of each parameter (scalar, integer, enum;
  function/table/unknown shown read-only for now) with units and schema
  descriptions; the Inspector is designed to host future parameter-centric views
  (Analysis, V2).
- Continuous validation surfaced in the Utility panel's Issues view (the single
  home for full issue text, parameter- and object-level) and an activity-bar
  Validation view; a non-modal review cursor walks issues in place.
- Global parameter/object navigation via a SearchPopup (Ctrl+F / Ctrl+P), backed
  by the single NavigationService that all navigation flows through.
- Edit scalar, integer and enum values through per-kind cards: Enter commits the
  raw editing state (valid or invalid), with an inline Reset and live validation.
- Distinct Save (write-back) and Export (copy-out) actions, an Import ▼ menu
  (Open File), and modified/backing-file tracking.
- State split into DocumentSession (per document) and AppState (active session +
  view state), preparing multi-document without exposing it.
- Export / round-trip as JSON or YAML.
- Use the command foundation for document operations:
  `core/commands.py`, `core/command_service.py`, `core/structure.py`,
  `core/document_factory.py`, and state-level undo support.

**Excluded from Version 1:** full function/table editors, visualisation, raw JSON
editing, file comparison, polished create-from-template UI, multi-file handling,
external database import, simulator hand-off, and any duplication of BPX logic.

## Version 2 — Complete editing, creation and visualisation

Creation, editing and visualisation are at the heart of the GUI, so creation is a first-class goal.

- Extend **per-kind editing cards** beyond Version 1: function expression
  editor, editable table grid, section add/remove controls, unknown/raw fallback,
  and compact quick inputs in parameter lists. The `Model` enum is the one
  special case, carrying a model-switch hook. See [architecture.md](architecture.md).
- **Actionable error workflows:** classify validation issues by an `IssueKind`
  enum (edit value, move misplaced field, choose model, map materials, add
  missing section, review warning) so the UI maps `kind → remediation` instead of
  branching on the underlying exception. Backed by a pure, unit-testable
  `core/remediation.py` that proposes fixed dicts. Includes closing the known gap
  where warnings lose their field path. See [architecture.md](architecture.md).
- Create new BPX files via UI workflows over the existing incomplete scaffolds
  for SPM, SPMe, DFN and Partial.
- Re-validate after edits (continuous).
- Visualise functions and interpolated tables (e.g. OCP plots) as an **Analysis
  view of the Inspector** — another view of the selected parameter — using
  `Function.to_python_function()`.
- Grow the Import ▼ menu (e.g. New Template) as create-from-template ships.
- Read-only raw JSON view.

## Version 3 - Validation beyond syntax and ecosystem connections

- **Sanity Check** - plausibility validation that visually compares parameter values against known / typical cell parameters, distict from the existing schema / syntax check. This will require a reference dataset of cell parameters (design-tension note in [architecture.md](architecture.md))
- **External database import** - pull parameters from open-source BPX databases such as LIIONDB, and other BPX databases, as additional sources.
- **Simulator hand-off** - export / hand BPX off to simulators, with **PyBOP** and **PyProBE** as the first targets; framed under simulator compatibility and standardisation. 


## Near-term organisation

- Keep Version 1 focused and shippable: Qt desktop app, open/navigate/validate,
  scalar/integer/enum editing, export, and a clean command foundation.
- Move deeper editing workflows into Version 2 rather than expanding Version 1
  indefinitely.
- Preserve strict layering so `state/` and `core/` remain reusable.
- Keep boundary coverage in `tests/test_boundaries.py` so `ui_qt/` stays out of
  `core/` and `state/`. See [architecture.md](architecture.md).

## Future

- Compare two BPX files (parameter diff and overlaid plots).
- Multi-file library / data management.
- Standalone distribution building on the PySide6 desktop frontend above.
- Further modelling-assistant features building on the simulator hand-off. 