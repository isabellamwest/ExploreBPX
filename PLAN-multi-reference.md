# PLAN — multi-reference comparison

## Status / handoff (2026-08-06, self-contained — session memory does not follow the repo)

**Phases 1 and 2 are on main and green (1658)**: `05214ef` Phase 1, `cb81f27` Phase 2. Signed wireframes (rev 3, the visual
reference for every surface): (internal design archive)
The Phase 1 build spec, showing what actually shipped and what rev 3 draws that is Phase 2/3:
(internal design archive)
**Next action: Phase 3 (scalar spread scale).**

Earlier commits on main: `3088779` Phase 0 pluralization · `adddc7b` Pull `source_label` ·
`85c6560` grouping helper + `core/spread.py` (+40 unit tests) · `02fee76` typography tokens
(separate track).

### Phase 1 departures from the signed design, all agreed 2026-08-06

- **Badge letters are mechanical.** First two alphanumerics, first capitalised, source case
  otherwise preserved: Chen2020→Ch, OKane2022→OK, AE-LFP→AE, Marquis2019→**Ma** (rev 3 drew
  "Mq", which no rule produces). On a collision **both** pins take first-letter-plus-ordinal
  (C1 / C3) — never one keeping "Ch".
- **Table values keep their grid in Phase 1**, showing the first pin that has the key,
  badge-labelled. Phase 2 turns that badge into rule 5's selector.
- **No per-row units in the ledger.** The main editor above shows one and the title carries it.
- **One badge size (18px) everywhere**, not rev 3's two.
- **Strip name elision is measured, not a breakpoint.** The strip lives in the parameter list's
  ~315px column, where a fixed threshold hid names even when one reference fitted.
- **Source page honesty pass** (Bella's call — the selector itself stays Phase 2): the reference
  pane header carries the shown pin's badge and reads "Reference 1 of N"; the stale band checks
  **every** pin and names the ones that changed; the Source pull now carries `source_label`.
  The last two were bugs the moment pinning began appending, not deferrals.
- **Open dialog**: "Replace reference"/"Add as reference" became one stable **"Pin as
  reference"**, disabled with the cap message at 4.

Badge palette validation (dataviz six-checks method, OKLab/Machado-2009 CVD): the chosen set
passes within-set — worst normal-vision ΔE 15.1 (floor 15), worst CVD ΔE 8.3 (target 8), white
badge text ≥ 4.5:1 on all four. Nearest reserved-colour neighbour is the slate vs accent
blue/purple chrome (ΔE 7–8) — accepted; badge letters are the secondary encoding. A slate
lightness-ramp alternative was considered and rejected; a two-hues×two-lightness set FAILED
CVD (ΔE 1.6) — never revisit it.

macOS note: the typography module pins `Segoe UI Variable Text, Segoe UI, system-ui` — on a
Mac it falls through to system-ui, so on-screen proof there renders different metrics than the
signed Windows screenshots; the offscreen suite is unaffected. Judge layout rules, not glyphs.

Unrelated carry-over so it isn't lost with the old machine's session memory: the typography
track left two open on-screen questions — Source-page mono density (Courier 12px → Cascadia
13px) and whether the card-header symbol wants `SYMBOL_OPTICAL_SCALE` above 1.0.

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

### Phase 1 — Surface B: pin-append, identity, Workspace, strip, Ledger, gutter  ✅ done (`05214ef`)
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

### Phase 2 — Surface C: overlay + table selector + source-page selector  ✅ done (`cb81f27`)

Departures agreed while building, 2026-08-06:

- **One selector grammar, two surfaces.** A checkable badge
  (`badges.ReferenceBadgeButton`) where **filled means present on screen**:
  in the chart legend "this curve is drawn", in the grid selector and the
  Source pane "these are the numbers you are reading". Rev 3 drew a ring
  around a filled badge for the grid; filled-vs-hollow reuses one idiom and
  keeps the no-tick/no-cross rule.
- **References equal to main are absent from the grid selector and the
  chart.** Their column would repeat the editor's own numbers and their
  curve would lie exactly under the main line, so a badge for them promises
  something the eye cannot find. They keep their quiet "same" ledger row.
- **The Source page's "Reference 1 of N" ordinal is gone** — the selector
  itself now says which, so the ordinal was saying it twice. `reload_reference`
  takes a pin index and the ← pull arrows read the page's selection.
- The chart's dashed purple single-reference line is retired: curves are
  solid, in badge colours, thinner than main's own.
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
