# PLAN — Validation preview & compare (Concept B)

**Status: draft, awaiting Bella's sign-off on the open decisions below.** Concept B
("Preview on the card, Compare means compare") was chosen 2026-08-12 from the
three-concept wireframe artifact
((internal design archive)), with the
instruction to develop the plan further and fold in the parameter column. A second
adversarial pass (same day) revised V11, V12 and V15 and added V17 and V18 — the
revisions are marked below. Nothing is implemented until the open decisions are
signed. Delete this file when the track ships; durable behaviour goes to
docs/architecture.md.

## Problems being solved

- **P1** No preview of a run's own data exists on the card; the only chart lives
  inside the "Compare…" dialog, so Compare secretly is the preview.
- **P2** The dialog rail says "Reference runs", colliding with the pinned purple
  reference system (a different feature with different data, colours and actions).
- **P3** Three data origins (bundled About:Energy samples, user-opened files, the
  active run) mix unlabelled; About:Energy/CC BY-SA provenance is never shown.
- **P4** Dialog formatting: own chip reads `nmc_pouch_cell.json` while references
  read `LFP 18650 cell · C/20 discharge`; a stray stretch leaves a dead zone with a
  floating Close; chip selection ring only means anything in Table mode; the
  numbers table is unstyled.
- **P5** The empty-run dropzone accepts drops but shows no affordance ever.
- **P6** Two comparison languages sit adjacent (purple reference bars in the list,
  a "Compare…" button meaning something else on the card).
- **P7** (found in the rethink) "Compare…" cannot compare the file's own runs
  against each other: the rail offers only bundled samples and other files, so
  overlaying your 1C against your 2C means saving and re-opening your own file
  through "Open BPX file…".

Parameter-column findings (verified 2026-08-12):

- **PC-a** Row order is raw JSON insertion order; the grid is always schema order.
  The two can disagree, and "Move up/down" on schema arrays shuffles only the JSON.
- **PC-b** An empty run `{}` lists zero rows while the card shows three placeholder
  columns; the deliberately suppressed "fields to add" group leaves no trace of the
  missing arrays in the column.
- **PC-c** Series row tooltips are the raw array as JSON, truncated at 400 chars;
  a differs-row tooltip adds one truncated JSON dump per pinned reference.
- **PC-d** BUG: a custom Series field under a run (Add parameter → Custom → Series,
  or any list-valued custom key) is kind SERIES, so `inspector.py` reroutes it to
  ExperimentCard — which builds columns strictly from `KNOWN_ALIASES`, shows no
  column for it, and leaves it uneditable from the middle column. No test covers it.
- **PC-e** A ghost (reference-only) array row, e.g. `Temperature [K]`, opens
  GhostParameterCard, not ExperimentCard; "Use" pulls the whole array via
  `PullParameter` in one undo step. This works but is entirely untested.
- **PC-f** The `("Validation",)` node is illogical end to end: the header count
  reads 0 (runs are child nodes, not parameters), the column below is empty, and
  "+ Add" opens the *parameter* popup whose Suggested group is empty and whose
  "Other parameters" list would write non-Validation keys under `Validation`.

## Decisions

Locked by the concept choice:

- **V1** Preview band on ExperimentCard; the compare dialog stays a modal,
  stateless, disposable viewer (lead-architect ruling unchanged). Button keeps the
  name "Compare…"; dialog title becomes `Compare · <run label>` (drop
  "· Experiment").
- **V4** Rail heading becomes "Compare with" (rendered caps per the app's rail
  style); "reference" is retired from every string in this dialog. Cap message:
  "Up to 4 runs at a time. Remove one to add another."
- **V5** Origin captions under each group heading: "Sample data · About:Energy"
  for bundled groups, "Opened file" for user files ("This file" for the V17
  group). One MICRO muted line at the rail foot:
  "Samples: About:Energy · CC BY-SA 4.0".
- **V6** One label rule everywhere (chips, numbers table, hover readouts):
  `<stem> · <run>`, never a file extension, own run included; fallback
  "Active file · <run>" for an unsaved document. Fixes the `.json` chip.
- **V7** Dead zone removed: no stretch inside the chart scroll area, dialog sized
  to content, Close in a real footer under a hairline rule.
- **V9** Table mode gets an explicit run selector beside the Chart/Table strip;
  the chip selection ring is removed entirely. Chips stay in both modes — their
  remaining jobs are legend-near-the-charts and per-run removal, which both modes
  need; the swatch+name repeat in the numbers table is the conventional
  chart-legend/facts-table pairing, kept deliberately.
- **V13** Bug fix: the ExperimentCard reroute predicate also requires
  `parameter.label in KNOWN_ALIASES`; a custom Series under a run gets SeriesCard
  (kept alive for exactly this) with its inline preview.
- **V14** Ghost array rows keep GhostParameterCard + "Use" (global ghost
  consistency wins over the unified-run-editor invariant); behaviour gains tests.
  Delete/Remove stays available on schema arrays — removing one is surfaced by
  the validator, not prevented by the UI (validator fidelity).
- **V16** Dropzone: dashed border + tint appear only while a file drag is over the
  card, invisible otherwise. An affordance, not copy.

Open, need Bella's word (recommendation first):

- **V2 Preview band layout.** Recommend: Voltage and Current charts side by side
  under the grid toolbar, fixed height ≈160 px, Temperature joining as a third
  when the column exists (three panels share the width; tick density is already
  adaptive from the chart-clarity work — cramped-axis check lands in the proof
  phase). Alternative: stacked full-width panels (more resolution, costs grid
  height). Height budget is safe either way: the inspector pane is one scrolling
  page, so the rule is grid keeps a preferred minimum (~8 rows) and short windows
  scroll.
- **V3 Band caption.** Recommend: none — a chart of your own data directly under
  the grid needs no label, and minimal chrome is the standing rule. Alternative:
  one MICRO muted "Preview" eyebrow.
- **V8 Numbers table columns.** Recommend: keep all five (Run, Points, Duration,
  Current range, Voltage range) — facts only, restyled (MICRO muted headers,
  tabular numerals, hairline rules, swatches on the app's dot scale, width aligned
  with the charts).
- **V10 Row order under a run.** Recommend: list schema arrays in schema order
  (Time, Current, Voltage, Temperature), then custom keys in file order;
  "Move up/down" disappears for schema arrays (their order is meaningless
  everywhere else) and stays for custom keys. Alternative: leave file order and
  accept the list/grid mismatch.
- **V11 Placeholder rows** *(revised in the rethink)*. Recommend: a run node also
  lists its missing schema arrays as muted placeholder rows (ghost-grey label,
  meta "not in file", no purple bar, no context menu); clicking one focuses that
  column on the card. Nothing is written until the user types — this mirrors the
  placeholder columns the card already shows, closing PC-b. Two rules from the
  rethink: (a) **a ghost row for the same key wins** — when a pinned reference
  supplies the array, the purple ghost row shows and the placeholder is
  suppressed, never both; (b) placeholder click needs its own signal (it has no
  parameter to select) routing to ExperimentCard focused on the alias — plumbing
  noted for the phase. Alternative: leave absent arrays invisible in the column.
- **V12 Series tooltips** *(revised: endpoints dropped)*. Recommend: for SERIES
  rows app-wide, the tooltip is simply `series · N values`, and differs-row
  reference lines become `<name>: series · N values` — no JSON dumps, and no
  first/last endpoints (rethink: "4.19 to 2.9" reads as a range and misleads for
  non-monotonic series; the card is one click away for the data itself).
- **V15 The Validation container node** *(revised: count fix alone was
  illogical — a count of 5 above zero rows breaks the count's meaning)*.
  Recommend: selecting `("Validation",)` lists one navigable row per run (name +
  muted meta `<n> arrays`), clicking a row navigates to that run's card; the
  header count then equals the rows below it naturally. And the node's "+ Add"
  button opens the experiment-name popup (same as the tree's "Add experiment…"),
  not the parameter popup — creating experiments is the only sensible add here.
  Alternative: leave the column empty and only suppress the count.
- **V17 "This file" rail group** *(new in the rethink — fixes P7)*. Recommend:
  the rail's first group is the active document's other runs (committed values;
  heading `<stem>`, caption "This file", unsaved fallback "Active file"; the
  card's own run is excluded — it is already the anchor). Comparing your C/2
  against your 1C becomes two clicks instead of save-and-reopen. The anchor stays
  the live draft; this-file rows are committed values — the anchor is "what you
  are editing", the rows are "what the file says", recorded so the difference is
  deliberate.
- **V18 Band visibility** *(new in the rethink)*. Recommend: the preview band is
  hidden while the dropzone shows (a fully empty run would otherwise stack three
  empty states — dropzone button, empty grid, empty charts) and appears with the
  first value. Panel empty texts are preview-worded (`No Voltage [V] values
  yet.`), never the dialog's comparison wording; a panel whose Y column has
  values but Time is empty says `No Time [s] values to plot against.`

## Phases

Each phase ends with a green `python -m pytest` from the repo root and stops
before commit for Bella's message. Order chosen so every phase is independently
shippable.

**Phase 0 — custom-series routing bug (V13).**
`inspector.py` reroute predicate gains the `KNOWN_ALIASES` membership check;
tests: custom Series under a run opens SeriesCard and is editable; schema arrays
still reach ExperimentCard. Small, no visual change for valid files.

**Phase 1 — compare dialog naming and structure (V1, V4-V7).**
Rail heading, origin captions, provenance line, cap wording, `_own_series_label`
extension strip, window title, footer + Close, stretch removal, content-fit
sizing. Updates the string-pinning tests in `tests/test_database_examples_dialog.py`
and `tests/ui_driver.py`; new tests: provenance line present, own label carries
run name and no extension, no rail string contains "reference".

**Phase 2 — numbers table restyle and Table-mode selector (V8, V9).**
Table restyle per V8; run selector combo; chip ring removal (chips keep swatch,
label, × for removable runs, in both modes). Tests: selector drives the table
page; chips carry no selection state; header/format strings updated.

**Phase 3 — "This file" rail group (V17).**
Dialog gains the active document's other runs as the first group, built from the
committed document (not the draft), current run excluded, ids distinct from
sample/file ids. Tests: group present with the right runs, current run absent,
committed-not-draft values, add/remove round-trip, cap counts them, unsaved-doc
heading.

**Phase 4 — card preview band (V2, V3, V18).**
Reuse `MultiSeriesChart` (empty-state text, hover readout, non-finite skipping
already built) with one accent-coloured series per panel; fed from the live grid
draft through a coalescing QTimer (≈120 ms) so 1000-point runs don't redraw per
keystroke; hidden while the dropzone shows (V18); panels pair
`min(len(Time), len(Y))` samples. Size policy: band fixed height, grid keeps a
preferred minimum, the already-scrolling inspector page absorbs the rest;
verified at the 900x560 minimum window. AppDriver seams
(`experiment_preview_series`, `experiment_preview_panels`) + tests: band
reflects committed value, reflects an uncommitted draft edit live, hidden on an
empty run, appears with the first value, Temperature panel appears with the
column, empty texts per V18.
`test_experiment_card_offers_its_grid_for_the_pages_leftover_height` updated to
the new split.

**Phase 5 — parameter column coherence (V10, V11, V12, V15).**
Schema-order rows + Move up/down gating; placeholder rows (ghost-precedence rule,
new focus signal, writes nothing); series tooltip summaries (shared helper in
`parameter_row.py`; differs-tooltip reference lines switch to previews);
container run rows + count + "+ Add" opens the experiment-name popup. Tests:
order pinned, placeholder anatomy + click focuses column + writes nothing +
suppressed when a ghost exists, tooltip formats, ghost `Temperature [K]` row
under a run renders and "Use" pulls the whole array in one undo step (closes
PC-e), container rows navigate and count matches, container add creates an
experiment.

**Phase 6 — dropzone drag affordance (V16).**
dragEnter/dragLeave styling on `_CsvDropzone`; test: property/objectName state
flips during a simulated drag, never set at rest.

**Phase 7 — proof.**
Real-app screenshots (`/run`, dialog-free seams per the screenshot recipe)
compared against the artifact wireframes; divergences reported honestly.
`overview/images/experiment.png` and `compare_dialog.png` re-captured (both are
stale — the current experiment.png shows an "Expand" control that no longer
exists). docs/architecture.md updated with the durable behaviour; this PLAN
deleted on ship.

## Risks and edge cases

- **Chart redraw cost**: 1000-point arrays × three panels on every keystroke —
  the coalescing timer is the guard; the sample-count chip already proves the
  draft-change hook exists.
- **Mismatched column lengths**: panels plot `min(len(Time), len(Y))` pairs, the
  established MultiSeriesChart behaviour; no invented pairing rules.
- **Non-numeric cells**: skipped by the existing chart helpers; never an error in
  the preview band (the grid's ERROR tint already carries that message).
- **Placeholder vs ghost precedence (V11)**: the same key must never render
  twice; ghost wins, pinned by a test.
- **Offscreen suite limits**: chart pixels can't be asserted headless; tests
  assert series data handed to the chart via driver seams, and Phase 7 carries the
  visual burden (per the offscreen-misses-native-bugs rule).
- **Typography/QSS**: all new text uses typography rungs; no font literals in
  ui_qt (guard test); no em dashes in UI strings; " · " separators throughout.
- **Symbols**: no circled ticks anywhere (standing rule); picker rows keep the
  plain tick; swatches follow the dot language sizes.
- **Palette**: compare dialog keeps `CHART_SERIES` + accent, never purple —
  purple stays exclusively the pinned-reference language (P6 word fix lands in
  Phase 1; the purple bars themselves are governed by the multi-reference design
  and do not change here).
- **Validator fidelity**: untouched — no new validation, wording, or spec logic;
  the preview band renders values, never judges them; deleting schema arrays
  stays possible and validator-surfaced (V14).
