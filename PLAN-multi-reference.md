# PLAN — multi-reference comparison

Signed design (2026-08-05, Isabella): up to **4 pinned read-only references**
(hard cap, 5th rejected with a message), ordered by pin time, each with stable identity =
two-letter badge + colour by pin order. Pinning **appends** (silent replace dies).
`swap_roles` / "Make main" **retired**. Persistence across restart and pin reorder
**deferred**. Wireframe rev 3 (agreed artifact) is the visual reference for all phases —
no further wireframe passes needed unless a surface drifts from it.

Badge palette (validated, pin order 1..4): `#0c8581` teal · `#5563c9` slate ·
`#8f3167` plum · `#79670b` olive. Reserved and never badge colours: reference purple,
accent blue, severity red/amber/green.

## Design rules per surface

1. **Workspace** — "Reference document" section becomes **References**: collapsed row per
   pin (badge, name, model, Remove — no validity dot); click expands full detail (Origin,
   Validity as dot+text, Model · BPX version, Contents, Citation for library sets / File
   path for file refs). Footer keeps both entry buttons + "N of 4 pinned"; buttons disable
   at cap. Library dialog wording moves to pin semantics.
2. **ComparisonStrip** — identity chips only (badge + name), fully quiet; per-reference
   counts in chip tooltip; elide to badges when narrow, never wrap. No controls.
3. **Card Ledger** — one row per distinct reference value; identical values group (stacked
   badges, auto-width cluster); row shows value + muted "same" (equals main) or a Pull
   button (differs). Absent key (MAIN_ONLY) = no row. Pull per row, undoable, undo names
   the group's first-pinned source: `Pull "Thickness [m]" from Chen2020`.
4. **Scalar spread scale** (numeric scalar/integer only) — 1-D axis under the rows; ticks
   per distinct value in badge colour, pin-order dot stack when coincident; main value =
   darker/taller marker; bounds = min/max of union + padding; log only when spread > ~2
   decades AND all values same-sign nonzero, axis always labeled linear/log; hidden when
   all values coincide or <2 distinct points; hover tick = names + exact value; **no
   click-to-pull**. Geometry in `core/spread.py`; UI paints only.
5. **Function/table overlay** — N reference curves in badge colours, main emphasised;
   never extrapolate (curves stop at their own domain edge, no inline annotation); legend =
   Main swatch + badge per ref with the key; hover badge = name/domain/point count; click
   toggles curve. Table mode: reference grid gains a badge selector, one reference's table
   at a time, default first pinned; refs lacking the key absent from selector.
6. **Tree gutter** — existing 3px purple bar; rule = differs from **any** pinned reference;
   the differ-count paint is deleted (a single count is meaningless against N references).
7. **Source page** — stays two panes; the reference pane gains a selector choosing which
   pinned reference it shows (Phase 2). Stale band / pull arrow act on the selected
   reference.

Hard rules: every mark is a stated value from a real file — no statistics, means, bands, or
good/bad colouring; never styled as validation; all spec logic stays in `bpx` via
`core/bpx_gateway.py`; writes only via explicit undoable source-named Pull.

## Decisions (resolved 2026-08-05)

- **D1 · Badge colour stability on removal.** Colour = current list index; removing an
  earlier pin shifts later colours. No extra state.
- **D2 · "New from existing file" at cap.** Still creates the new document; the source is
  not pinned and a message says so ("4 already pinned").

## Phases

Groundwork already on main ahead of the UI phases: Pull `source_label` (undo wording
unchanged until real sources are wired), `compare.group_reference_values`, and
`core/spread.py` — all with unit tests. New UI must use `app/ui_qt/typography.py`
tokens (the typography track landed before Phase 1 started).

### Phase 0 — pluralize, zero visual change  ✅ done: suite green, app identical
- `app/state/app_state.py`: `reference: ReferenceSnapshot | None` → `references:
  list[ReferenceSnapshot]`; all mutators keep today's replace-on-open semantics against
  `references[0]`; temporary read-only `reference` property for call sites deferred to
  later phases (Source page). `swap_roles` still works this phase.
- `app/ui_qt/main_window.py`: `_recompute_comparison` builds `list[ComparisonResult]`
  (one `compare()` per snapshot; N full recomputes accepted — no caching in this track);
  `_apply_comparison` threads lists everywhere.
- Pluralize consumer signatures, internals still index-0: `tree_model.set_comparison`,
  `parameter_list.set_comparison`, `inspector.set_comparison`, `comparison_strip.set_state`,
  `workspace_panel.set_state`/`_set_reference`.
- No new tests; existing suite unchanged and green is the acceptance gate. After the
  rename, grep `state.reference`-singular reads — only intentional deferrals may remain.

### Phase 1 — Surface B: pin-append, identity, Workspace, strip, Ledger, gutter
- State: `open_reference`/`open_reference_set` → `pin_reference`/`pin_reference_set`
  (append + cap outcome `AT_CAP`); `remove_reference(pin)` takes an argument; delete
  `swap_roles`; `new_from_file` routes through the pin path (D2).
- Commands: `PullParameter`/`PullSection` gain `source_label`; label becomes
  `Pull "<key>" from <source>`.
- New `app/ui_qt/reference_identity.py`: pin-order colours (tokens in `style.py`),
  pure `badge_letters()` (two chars from display name; collision → first letter + pin
  ordinal; recomputed per pin change, never persisted), `ReferencePin` composite
  (snapshot, comparison, letters, colour) threaded to consumers.
- Workspace References section per design rule 1; remove "Make main" wiring;
  `remove_reference_requested` carries the pin; library dialog wording + cap handling
  (block/disable at 4).
- Strip chips per rule 2. Ledger per rule 3 — grouping helper (pure, over `RowDiff`s using
  `raw_equal`) lives in `core/compare.py`; `ghost_card.py` (REF_ONLY) gets the same
  grouping. Gutter per rule 6 (delete `REF_COUNT_ROLE`/`_ref_count`).
- Tests: delete `test_make_main.py`; rewrite reference open/library flows for append/cap;
  `test_comparison_ui.py` fixtures become `main_and_refs(n)` exercising real grouping;
  workspace tests for rows/expand/cap; `ui_driver.py` pin-row helpers; pure collision test.
- Qt risks: dynamic row rebuild must not leak stale button connections (rebuild rows
  wholesale per `set_comparison`, matching inspector refresh-in-place discipline).

### Phase 2 — Surface C: overlay + table selector + source-page selector
- `table_preview.py`: single `_ref_line` slot → per-pin series with badge-colour pens;
  dynamic legend (Main + badge per ref with key), legend-row-based hover/click (not
  chart-canvas picking); no extrapolation (never merge points across references).
- `cards/function.py` / `base.py` / `table.py` `set_reference_table` become per-pin lists,
  reusing Phase 1's "which pins have this key" filtering.
- Badge selector above `ReferenceTableGrid` per rule 5.
- Source page selector per rule 7; pane header shows the selected pin's badge + name.
- Tests: overlay count/legend/toggle/domain-stop; selector default/switch/absent-key;
  source-page selector switching. Respect the QtCharts import guard in every new path.

### Phase 3 — Surface D: scalar spread scale
- New `app/core/spread.py` (pure, badge-ignorant — plain values in, geometry out): bounds +
  padding, log/linear decision, coincident grouping, hidden-state rule. 3-4 functions, no Qt.
- New `app/ui_qt/cards/spread_scale.py` painted widget per rule 4; wired into
  `parameter_card.py` gated on numeric kinds via existing `ParameterKind` machinery
  (never a fresh numeric sniff).
- Tests: pure unit tests for all geometry rules (incl. mixed-sign never-log); AppDriver +
  screenshot for visibility rules, hover, marker styling.

## Process
- Each phase: `python -m pytest` headless from repo root, honest report (matplotlib absent
  from `.venv`; two `PyparsingDeprecationWarning`s expected). `test_boundaries.py` after
  every phase — `core/spread.py` and the compare grouping helper must stay Qt-free.
- Commit per phase, only when asked; on-screen screenshot proof against wireframe rev 3
  after each UI phase.
