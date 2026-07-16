# PLAN — Validation-section experiment editor (Concept C, approved 2026-07-16)

Redesign of how the BPX `Validation` data section (user-named experiment runs, each
with row-aligned `Time [s]` / `Current [A]` / `Voltage [V]` / optional
`Temperature [K]` arrays) is edited. Approved concept: **import-first experiment
card** — one unified multi-column grid per run, CSV as the front door, guided empty
states. Wireframe and full design rationale:

- Concepts: (internal design archive)
- Approved wireframe: (internal design archive)
- Phased design: (internal design archive)

## Locked decisions

- **D1a** — run node and any of its array parameters open the *same* `ExperimentCard`;
  the focused-column ring is derived purely from which path navigation resolved
  (bare run node → no focus). All columns always editable.
- **D2b** — "＋ Temperature [K]" is a card-toolbar button (shown only while absent);
  the parameter list's "fields to add" group offers it too, for free.
- **D3a** — guided empty state only when the section exists with zero runs; an absent
  section keeps the generic root "Add section" flow, no special-casing.
- **D4a** — CSV mapping confirmation reuses `CsvImportDialog` unchanged; visible
  mapping the user confirms, never silent coercion.
- **D5a** — the parameter list keeps all per-array rows (with ⚠/count markers).
- **D6a** — a typed cell edit commits only the one array that changed; `SetValues`
  is reserved for genuinely multi-array operations (CSV import, add-Temperature).
- **D7** — paste stays per-column; synchronized multi-column paste out of scope.
- Ragged column lengths are the *normal* case — bpx is the sole judge of mismatches;
  the card displays diagnostics, never computes them. (Note: current bpx has **no**
  cross-array length validator, so the mismatch chip is dormant by fidelity —
  pinned by test.)
- `ExperimentCard` must stay renderable read-only (future Reference-document
  Workspace; see docs/05-future.md).

## Phases

- [x] **Phase 0 — multi-column grid model.** `MultiColumnGrid`/`_MultiColumnGridModel`
  appended to `app/ui_qt/cards/grid.py` (independently-lengthed all-editable columns,
  per-column insert/remove, `{(row,col): msg}` tinting, `read_only` flag).
  `NumericGrid` untouched. Tests: `tests/test_numeric_grid_multicolumn.py`.
- [x] **Phase 1 — `ExperimentCard` + routing.** `app/ui_qt/cards/experiment.py`;
  Inspector `reveal()` routes any `("Validation", <run>)` target (bare node or SERIES
  parameter) to the card; `experiment_cells` in `cards/cell_issues.py`; CSV import as
  one undo step; per-column paste; "＋ Temperature [K]" commits `[]`. SERIES params
  that aren't known arrays keep their ordinary card. Tests:
  `tests/test_experiment_card.py`. Suite green at 1039.
- [ ] **Phase 2 — retire `SeriesCard`.** Registry cleanup; deletion of
  `cards/series.py` awaits explicit sign-off (recommendation: delete; git history
  keeps it recoverable).
- [ ] **Phase 3 — import-first entry for empty runs.** Dropzone + Browse above the
  still-usable empty grid when all arrays are absent/empty (derived display state);
  same CSV pipeline; dismisses on first data, returns on undo. Also: expand-to-pane
  parity for `MultiColumnGrid` (gap vs `NumericGrid.expand_toggled`), per-column
  sample-count footer chip, 10k-row perf smoke (report-only).
- [ ] **Phase 4 — guided empty state (zero runs).** Selecting `("Validation",)` with
  no runs shows "No experiments yet" + **＋ Add experiment** (existing AddSection
  flow as a button) and **Import CSV as new experiment…** (deliberately two undo
  steps: add run, then fill — undoing the import keeps the named run).
- [ ] **Wrap-up.** Prove the build matches the approved wireframe (AppDriver tests
  AND real-app screenshots), sync docs/02-ui.md + docs/03-features.md, full-suite
  green check.

## Constraints

Tree stays the single navigation (no run tabs). Layer boundaries `core ← state ←
ui_qt` (tests/test_boundaries.py). All bpx contact through `app/core/bpx_gateway.py`;
no hand-rolled spec logic. Commit only on request; never push.
