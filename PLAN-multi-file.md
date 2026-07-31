# PLAN — Multi-file track (main + reference)

> **⚠ This is a plan, not a spec — a proposal that can change, not a locked
> requirement.** Where it and the running app differ, the app is correct. Re-check
> against the code and confirm with Bella before acting on anything still open.

**Audience: a future working session (or the user), executing without this
conversation's context.** Read top-to-bottom before touching code; do not
re-derive or relitigate. Design discussed and signed with Bella 2026-07-21 over
four review rounds. Design of record (wireframes + rationale + rejected
alternatives): (internal design archive)

Anchored at commit `85c2029` ("docs: add brainstorm idea pool"); working tree has
`PLAN-app-audit.md` modified (separate active track). Suite baseline **1249
passing** per the app-audit Phase A baseline, 2026-07-21. Implementation starts
**only on Bella's explicit go**, milestone by milestone.

**Status 2026-07-21 (end of day):**
- **M1a committed** (`9bacdf4`); M1b (New from source, 4c) approved in principle
  but **parked** — Bella wants it refined before build; entry point undecided.
- **M2 built and verified, uncommitted** — suite **1330 green** on a tree that
  also carries the (separately owned) Workspace-restyle session's uncommitted
  work. Rev 3 build wireframes (signed):
  (internal design archive)
- **M3 built and verified 2026-07-22, uncommitted** — hide toggle removed
  everywhere; stacked "Main file"/"Reference file" card + ghost card with
  Copy up (solid purple, disabled when equal); `PullParameter`/`PullSection`
  core commands (verbatim, ancestor-creating, one undo entry; section pull
  UI waits for M5); 5c pinned live (bpx itself reports a dangling particle
  name via the Initial-hysteresis-state key-match error, and "Field
  required" for half-built particles — the app invents nothing). Suite
  1358 green; real-window screenshots match the signed wireframes.
  *Amendment (Bella, 2026-07-22): the card description now sits directly
  under the parameter title in BOTH modes (it used to sit below the
  editor) — consistent position whether or not a reference is docked.*
  Signed M3 wireframes:
  (internal design archive)
- **M4 wireframes signed 2026-07-22** (Concept A, card action — Bella chose A
  of three concepts; B swap-rail and C role-handoff-dialog rejected, C's
  role-naming line folded into A's prompt). Signed M4 wireframes:
  (internal design archive)
- **M4 built and verified 2026-07-22, uncommitted** (M3 landed first as
  9ab9bfd). Make main + Remove on the reference card; `SwitchIntent` +
  `_ask_switch_intent` seam (mirrors `_ask_open_intent`);
  `AppState.swap_roles` loads both files from disk before mutating either
  role, so any load failure leaves roles untouched; promote-without-demote
  fallback (no main open, or never-saved main discarded) promotes and
  undocks the reference. Independently reviewed (accept; both flagged gaps
  closed: fallback-branch tests added, real-window pass done). Suite 1373
  green (15 M4 tests incl. one real-QMessageBox); real-window screenshots
  match the signed Concept A frames. *As-built note: the dialog button
  labels need Qt's "&&" escape — a lone "&" is a mnemonic marker and the
  native style renders "Save  switch"; caught only in the real-window
  pass, invisible offscreen.*
- **M4 committed** `ee0382d` 2026-07-22 (suite re-verified 1373 green at the
  commit).
- **M5 redesigned and signed 2026-07-22 (four review revs with Bella): the
  Compare page became the SOURCE page**, a raw-JSON split diff inspired by
  semanticdiff/diffchecker with BPX tree intelligence. Signed frames:
  (internal design archive)
  Decisions 2/13/15 amended below; the Workspace doorway idea (counts line +
  Compare action on the reference card) is rejected. Build awaits Bella's
  explicit go.
- **M5 build IN PROGRESS 2026-07-22, uncommitted** — building step by step
  with a check-in after each step; suite **1409 green** after step 2. Step
  plan: (1) core row model ✔; (2) rail entry + single-pane page ✔;
  (3) two-pane aligned rendering + shared folding + gaps ✔; (4) value-only
  highlight chips ✔; (5) ← gutter pulls ✔; (6) toolbar (‹ › stepper, ⇄ Make
  main, stale band); (7) Up/Down navigation + double-click Editor jump;
  (8) real-window verification. Built so far:
  - `app/core/source_rows.py` (+ `tests/test_source_rows.py`, 14 tests):
    pure aligned row model. `build_rows(main_raw, ref_raw=None)` walks the
    raw dicts in true document order (sections/leaves interleaved); ref-only
    keys/sections slot in after the nearest preceding shared key in the
    reference's own order; states looked up from `core.compare.compare`
    (never recomputed — rule 14); `ref_raw=None` = single-pane mode;
    `closable` marks dict/list leaves; `is_difference` marks stepper
    targets (ghost section header included, main-only excluded).
    Presentation ORDER lives here, not in compare.py, on purpose.
  - `app/ui_qt/source_page.py` (+ `tests/test_source_page.py`, 12 tests):
    `SourcePage` (toolbar + "◇ Open a reference to compare…" hint) over
    `SourceView`, a custom read-only `QAbstractScrollArea` painting
    monospace JSON lines — bold section headers with carets + muted
    "n parameters" sizes, tables whole/closable to `"key": table`, fold
    state preserved across re-renders and pruned for vanished paths, no
    input widgets. Deliberately NOT built on `BpxTreeModel`/QTreeView:
    custom painting is the path to step 3's aligned panes, chips, gutter.
  - `main_window.py`: `_SOURCE_PAGE_INDEX = 3`; rail entry between Editor
    and Diagnostics; refresh pushed from `_apply_comparison` (the existing
    fan-out — edits/undo/open/dock all reach it); rail button disabled with
    no document; falls back to Workspace if the document ever goes away
    while Source is current. `icons.py`: new `SOURCE` `</>` glyph.
    `tests/ui_driver.py`: `show_view("Source")` + line/fold/hint readers.
  - Step 3 (2026-07-22, uncommitted): `SourceView` renders two aligned
    panes over one shared fold set (`_PaneLine` pairs): per-side section
    "n parameters" counts, flat NEUTRAL_TINT gap blocks where a side lacks
    the key, ref-only rows/sections in the reference purple, fillable keys
    grey with no value (signed F2 rendering), and open tables line-aligned
    with difflib.SequenceMatcher so a longer table's gaps sit beside its
    extra entries, not at the tail (caught by an offscreen paint smoke,
    invisible to the text-level tests). Centre gutter column reserved
    (40 px, the ← pulls land there in step 5); pane headers
    "Main · file · model" / "◇ Reference · file · model" above the panes;
    `refresh` now takes main_name/main_model from `_apply_comparison`.
    Driver: `source_ref_line_texts`, `source_pane_headers`. 11 new tests;
    suite 1416 green + 4 pre-existing environment-only failures on this
    machine (2 known keyboard-focus + 2 real-dialog; the venv's stale
    bpx 1.1.0 was synced to the committed 1.1.1 pin, which cleared 6
    other pre-existing failures).
  - Step 4 (2026-07-22, uncommitted): value-only chips over a new
    `style.DIFF_TINT` (#ffdfb8, the frames' chip wash, added to the
    palette like M2's REFERENCE_TINT). `_Segment.chip` painted as a
    rounded wash behind the segment. Placement: DIFFERS chips both
    sides' values -- token-level for string pairs (whitespace-token
    difflib, quotes stay outside the chip) so functions light only their
    changed segments; FILLABLE chips the reference-side value alone;
    open tables chip replace-paired entry lines on both sides (comma-only
    pairs and gap-facing extras stay plain; key/caret lines never chip);
    closed differing tables chip the "table" word; shared collapsed
    sections holding any difference append a chipped "  ⋯" (ref-only
    headers stay purple-without-chip; equal/main-only stay plain).
    Single-pane never chips. `SourceView.chipped_texts()` +
    driver `source_chipped_texts()`. 10 new tests; suite 1426 green +
    the same 4 environment-only failures (one toast timing flake passed
    on re-run). Offscreen screenshot matches F1/F2 chip placement.
  - Step 5 (2026-07-22, uncommitted): ← gutter pulls. `_Line.pull_path`
    marks the key line of every `is_difference` row (differs/fillable/
    ref-only params; ref-only section headers -- shared/collapsed headers
    and equal/main-only rows carry nothing, per the frames); the view
    paints the 26×20 chip (`REFERENCE_TINT` fill, new named
    `style.REFERENCE_BORDER` #d5cde6 outline -- the tone the inspector's
    reference chrome already used) centred in the gutter. A gutter click
    emits `pull_requested(path, is_section)` -- the gutter is ←-only, a
    chipless gutter click never toggles a fold -- and `MainWindow.
    _on_source_pull` resolves the reference's raw value at that path and
    executes the shared `PullParameter`/`PullSection`, then runs
    `_on_committed()` (commands do not self-propagate; this is the same
    post-commit refresh the inspector's Copy up uses -- forgetting it left
    the page stale, caught by the driver test). Ref-only children inside a
    ref-only section also carry their own ← (a single-param pull creates
    missing ancestors, per the M3 command contract). Driver:
    `source_pull_paths`, `source_pull`. 6 new tests (presence rules,
    QTest gutter/pane hit-testing, cross-page undo stack, one-undo-entry
    section pull, live re-render after pull); suite 1432 green + the same
    4 environment-only failures. Offscreen screenshot matches F1's ←
    placement.
  - Step 6 (2026-07-31, uncommitted): toolbar + stale band, per the
    step-6 build frames (signed rev 2, as built:
    (internal design archive)).
    Two-pane toolbar: ‹ › difference stepper + thin separator + "⇄ Make
    main" (routes to the existing M4 `_on_make_main_requested`; the page
    adds no swap logic). Single-pane toolbar gains the F3 "filename ·
    model" label the step-2 build lacked. Stepper: targets are the row
    model's `is_difference` rows in file order; stepping unfolds closed
    ancestors, scrolls, and lands a `style.ACCENT` outline on both pane
    cells -- selection is NEW machinery (path-based, click-to-select,
    pruned when the row vanishes) that step 7's Up/Down will reuse.
    Settled calls: C1 zero differences = ‹ › disabled never hidden; C2
    wrap at both ends; C3 unreadable file at Reload = standard "Cannot
    open file" error, snapshot + band untouched (and a stat failure never
    conjures a band). Stale band under the pane headers ("The reference
    changed on disk · Reload"); mtime compared on notice only -- Source
    page entry, window activation (`changeEvent`), reference
    dock/swap/reload -- via `MainWindow._check_reference_stale`;
    `AppState.reload_reference` re-snapshots in the state layer. 17 new
    tests; suite 1449 green + the same 4 environment-only failures;
    real-window screenshots match all three frames.
    *Amendment (Bella, 2026-07-31): the ◇ reference glyph is dropped
    app-wide -- Source pane header and hint, the Editor comparison
    strip (now "Reference · {filename} · {model}"), and the ghost-row
    tag (now "REF ONLY"). Decisions 3/12/13's ◇ mentions read as
    superseded on this point.*
  - Step 7 (2026-07-31, uncommitted): keyboard + Editor jump. Up/Down move
    the selection one *visible* row at a time (folded children skipped,
    open-value continuation lines skipped), stopping at the ends -- arrows
    do not wrap; cycling stays the stepper's job. `SourceView` is now
    `StrongFocus` (still no input widget -- keys only move the selection)
    and `_show_page` focuses it on Source entry, so arrows work without a
    click. Double-click a row = the page's one Editor link: emits
    `navigate_requested` -> the shared `NavigationService` (which already
    switches to the Editor and fans out reveals). Emitted only for rows
    `in_main` -- a ref-only row navigates nowhere (the service's
    suffix-match fallback must never guess for it); the gutter is excluded
    (its press already pulled). 7 new tests incl. a real-key-event
    focus-on-entry pin; suite 1456 green + the same 4 environment-only
    failures; real-window run verified focus, a 5-row arrow walk, and the
    double-click landing on the right Editor card.
  - **Unlocked calls a later session may revisit with Bella**: rail order
    (Workspace·Editor·Source·Diagnostics); "n parameters" always shown on
    headers (not only folded, and per side in two-pane mode); lists close
    to the word "table" too (no separate word invented).
- M1 build wireframes (for the record):
  (internal design archive)
- **Per-milestone workflow (Bella)**: wireframes drawn and approved BEFORE each
  milestone's build; verify against the real window, not offscreen alone; STOP
  before committing with a suggested message; **commit messages must never
  contain track codes** ("M1", "4a", …). Multiple sessions work this repo
  concurrently — `git status` before assuming anything about the tree.

## 0. Working agreements

Same as `PLAN-completion-track.md` §0, in full. In particular: one milestone =
one commit, **STOP before every commit** and print a suggested message; delegate
straightforward implementation to `principal-engineer` with a tight brief; verify
empirically against the real app (offscreen) and the real validator; `matplotlib`
is missing from the venv; two `PyparsingDeprecationWarning`s from bpx are expected.

## 1. The model

- Exactly **one main** file: today's `DocumentSession` unchanged — undo/redo,
  dirty, save, live validation. Everything mutable hangs off it.
- At most **one reference**: a read-only snapshot (raw dict + filename + model +
  one-shot validation summary). No session, no undo, no dirty, no file watching.
  Loaded via `bpx_gateway.load_raw` + `validate` (the example-library pattern).
- **Two files maximum, ever.** Opening a second reference replaces the first
  (toast; nothing to lose — it's a snapshot). No chips, no N-way compare.
- **Model α switching**: "Make main" swaps roles. The demoted main's undo history
  does not survive; unsaved edits force the standard save-first dialog. Role
  assignment is a Workspace action, never on the undo stack.
- **UI copy rule (Bella, round 4): the app never says "your/yours".** Labels
  always name the role: "main" / "reference" ("main value", "3 main only",
  "not in the main file"). Chosen term is **main** (matches the tile tag).
- The standing no-circled-badges rule applies throughout.

## 2. Locked decisions (settled — do not reopen)

1. **Row matching**: full literal key, never position, never unit-converted.
   `Thickness [m]` ≠ `Thickness [µm]` — two distinct parameters, shown
   asymmetrically (user-guide note explains; no special handling).
2. **Difference = raw inequality of committed values**, per kind. Functions /
   tables / series show existing ghost summaries ("table · 12 pts") and tint on
   raw inequality. No numeric tolerance, no semantic curve diff. *Amended
   2026-07-22, Source page only: the page renders real raw values (functions
   in full, tables whole and closable); Editor rows keep their summaries.
   Difference remains raw inequality.*
3. **Row states**: equal · differs · fillable (empty main, value in ref) ·
   main-only (no tint — absence in a reference is not a defect) · ghost
   (ref-only row or whole ref-only section).
4. **Ghost treatment is loud, everywhere**: **purple** (`style.REFERENCE`)
   dashed border + purple tint + italic value + `◇ REF ONLY` tag (blue in the
   original design, superseded by the M1 purple amendment). Ghost-selected
   inspector card is headed "Not in the main file" and offers only Copy up.
5. **Copy up** (the only mutation; button label is exactly "Copy up" — the
   design's ↑ glyph was dropped by Bella's M3 sketch): verbatim copy
   reference → main. Destination exists → set; missing → add; missing
   ancestors → created in the same command. **One undo entry** always. Section
   pull = one batch entry. Copy up commits immediately and replaces any
   uncommitted card draft (undoable). Same-key different-shape copies
   verbatim; row + card re-classify from the new shape. **Disabled when the
   values are already equal** (a verbatim copy would be a no-op). One-way
   only — the reference is never a target.
6. **Validation**: reference validated once at load; issues shown on its
   Workspace tile only, never the Diagnostics page. Pulling from an invalid
   reference is allowed. **5c rule (Bella): dangling name-references (e.g.
   particle names) get NO invented diagnostic — the app shows exactly what the
   real bpx validator reports, or nothing.** Pin actual behaviour with a live
   validator test in M3.
7. **Cross-model compare is first-class** (DFN ↔ SPMe ↔ SPM ladder). Diff is
   keyed, never model-aware; model badges visible on tiles, Editor comparison
   strip, and Compare page header.
8. **Opening**: open/drop while a document is open asks Replace main vs Add as
   reference (4a); dedupe by path with quiet toast (4b); **New from source**
   (4c) clones a file into a fresh unsaved main and auto-docks the origin as
   reference.
9. **Closing (Bella's 6b)**: closing the main is just closing the main — normal
   dirty prompt, no "promote a reference" dialog. The reference stays as a
   Workspace tile; Editor shows the no-document state.
10. **Save As default folder** for never-saved mains (templates, 4c clones):
    Documents / last-used — never a bundled template/example directory. Cancel
    backs out of the whole surrounding flow (e.g. a pending switch).
11. **Stale reference on disk**: no file-watching; on notice (mtime check),
    a quiet "changed on disk · Reload" band. Never silent refresh.
12. **Editor comparison — REVISED by the workflow rethink (rev 3 wireframes,
    signed 2026-07-21, built as M2)**: the Editor keeps only edit-time aids;
    everything about *surveying* differences is Compare-page-only (M5).
    - Tree: per-section "≠ N" difference counts (text-append, like the ⚠
      marker). **No ghost tree nodes** — a section the main lacks is Compare's
      business.
    - List: row tints (differs/fillable, warning tint) + ghost rows (purple
      dashed + tint + italic value + "◇ REF ONLY" tag, read-only). **Merge
      rule (Bella): a key the main lacks that the reference has is a ghost
      row, absorbing its fields-to-add row; fields-to-add remains only for
      keys the reference lacks too. One key, one row.** No differences-only
      filter, no ‹ › walker in the Editor.
    - Comparison strip above the list: "◇ {filename} · {model}" + whole-file
      counts. **No hide control (Bella, 2026-07-21): a docked reference means
      comparison is wanted; the M2-built hide toggle is removed in M3.**
    - Inspector in comparison mode — **Bella's stacked layout (sketch,
      2026-07-21)**: a "Main file" heading over today's editable value row,
      then a "Reference file" heading over a purple-tinted read-only value row
      (units shown as in the main row) with the **Copy up** button beside it.
      Headings appear only while a reference is docked; with none, the card
      is exactly today's. Ghost card: "Not in the main file" + the Reference
      file section + Copy up only.
13. **Source page (REPLACED 2026-07-22; supersedes the round 3–4 Compare
    page; signed rev-4 frames linked in Status)**: a rail-tab sibling of
    Workspace/Editor/Diagnostics named **Source**, icon `</>`, enabled
    whenever a document is open. No reference docked: one full-width pane of
    the main file's formatted raw JSON (monospace, live against the session,
    collapsible section headers, "n parameters" sizes, quiet "◇ Open a
    reference to compare…" toolbar hint). Reference docked: two aligned panes
    (Main left, Reference right) of real JSON matched by full key, the whole
    file visible including equal rows — no fold-away, no differences-only
    filter. Common sections share ONE fold state across both panes; flat grey
    blocks mark a key absent on one side. Highlight chips on VALUES ONLY, no
    row washes: changed scalars, the changed segment of function strings,
    per-entry in tables, the word "table" on a closed differing table, and
    the ⋯ of a closed section containing differs/fillable/ref-only rows.
    **No difference counts and no "=" anywhere on the page** (Bella rejects
    the "n differ · n ref only" wording; the Editor strip keeps its counts
    for now). Ref-only = purple text plus the opposite gap, no ◇ REF ONLY
    tag on this page; fillable = grey key with no value, ref-side value
    chipped; main-only quiet. Copy = small light-purple-tint **←** in the
    centre gutter (differs / fillable / ref-only rows, table key-lines,
    ref-only section headers = whole-section pull, one undo entry); absent —
    not disabled — on equal and main-only rows. Toolbar: ‹ › difference
    stepper (unfolds its target) and ⇄ Make main only. Keyboard: Up/Down
    move the selection row by row through the file; ‹ › jump differences.
    Double-click a row → Editor at that parameter via `NavigationService`.
    Stale reference: slim neutral band under the pane headers ("The
    reference changed on disk · Reload"). Still rejected: sort-keys /
    ignore-array-order options, raw text diff, two-way merge, green/red
    palette.
14. **Coexistence rules**: one diff engine; one pull command shared by the
    Source ← and inspector Copy up (same session, same undo stack, Ctrl+Z
    from either page); Source owns its own scroll/selection/fold state — the
    only Editor link is the explicit double-click jump; **no input widget
    ever appears on the Source page**.
15. **Big kinds (AMENDED 2026-07-22)**: no modal viewer. Tables render whole
    in the Source panes by default, closable via the caret on their key line
    to a `"key": table` summary, the word "table" chipped when the tables
    differ. The grid's `read_only` mode stays unused.

Deferred (BRAINSTORM, not this track): N-file matrix, bulk pull beyond one
section, curve overlay plots, raw-JSON diff tab, second editable document.

## 3. Verified code anchors (2026-07-21)

- Editor 3-pane `QSplitter`: `app/ui_qt/editor_page.py:23`.
- Card's reserved reference slot: `app/ui_qt/cards/parameter_card.py:140` —
  trailing, beside the editor; the signed design stacks the block below the
  value row instead. Cosmetic call at build time; the reservation comment goes
  away either way.
- Synthetic-row precedent (ghost rows): "fields to add" group,
  `app/ui_qt/parameter_list.py:229`; rows render via `ParameterRowDelegate`.
- Tree ⚠ = display-text append: `app/ui_qt/tree_model.py:101`. **Ghost tree
  nodes are the one genuinely new mechanism** — `BpxTreeModel` has no node for
  a section the main lacks.
- `AppState` holds one optional session and anticipates more:
  `app/state/app_state.py:20`. Add `reference` beside `active`.
- Loading: `bpx_gateway.load_raw` (:101) + `validate` (:118). The example
  library (`app/core/example_library.py`) exposes only the Validation slice
  today — a whole-file handover seam is a small extension.
- Workspace tiles planned: `app/ui_qt/workspace_panel.py:97`.
- Navigation for click-through: `app/ui_qt/search.py` `navigation_requested` →
  shared `NavigationService`.
- The Validation-runs Compare… dialog (`database_examples_dialog.py`) is
  unrelated and stays as is.

## 4. Milestones (one commit each; STOP before committing)

**M1 — reference in state + Workspace.** `ReferenceSnapshot` (state layer;
frozen raw dict, path, model, validity summary, mtime), `AppState.reference` +
signals. Workspace: reference tile below the document card (name, model,
validity note, Remove), "Open as reference…" button, 4a dialog, 4b dedupe
toast, one-reference replace toast, 6b close behaviour, 4c New from source.
Tests: state snapshot round-trip, tile lifecycle via `AppDriver`, boundary
suite stays green. Usable alone: "keep a second file at hand".
*Amendment (2026-07-21, signed off with the Workspace Concept A restyle):
the reference feature's colour is **purple** (`style.REFERENCE`, #6f42c1),
not teal, and the tile is now a card with the exact anatomy of the document
card (title row + validity pill + key/value rows) marked only by a small
purple "Read-only" tag on its title row -- no side bar, no caps tag. Later
milestones reusing the reference colour (ghost rows, comparison strip)
inherit purple.*

**M2 — diff engine + comparison-aware Editor.** *Built 2026-07-21 per the
revised decision 12 (rev 3 wireframes).* `app/core/compare.py` (pure core):
keyed matching, typed raw equality (bool ≠ int, 1 ≠ 1.0), FILLABLE via the
completion machinery's None-only emptiness, sections = `core.tree_model`
object nodes; order-independence and 2h asymmetry pinned by unit tests. UI:
row tints + ghost rows (with the merge rule) + slim comparison strip; tree
"≠ N" appends; read-only inspector reference block + ghost card (pulled
forward from M3). Lazy recompute via `_refresh_all`. *As-built note: list
tints must be painted by the delegate — `QListWidgetItem.setBackground` is
silently ignored under a stylesheet that styles `::item` (pixel-tested).
The strip shipped with a hide toggle, since removed by decision 12.*

**M3 — Copy up + Bella's inspector layout.** *Signed 2026-07-21 (wireframes
linked in Status above); to be built by a separate session. Precondition:
land the uncommitted M2 + restyle work as commits first so this milestone
starts on a clean tree.* Order of work:
1. **Remove the hide toggle entirely** — the control, the collapsed
   "◇ show comparison" affordance, the hidden-state plumbing and its tests.
   The strip becomes a plain indicator: "◇ {filename} · {model}" + counts.
2. **Restyle the comparison card** to decision 12's stacked layout: "Main
   file" heading over today's editable value row; "Reference file" heading
   over a purple-tinted read-only value row (units shown as in the main
   row); **Copy up** as a solid purple (`style.REFERENCE`) button beside the
   reference row. Headings only while a reference is docked. Ghost card =
   "Not in the main file" + parameter name + Reference file row + Copy up.
3. **Core commands** `pull_parameter` / `pull_section` (verbatim,
   ancestor-creating, one undo entry each, decision 5 in full) wired to Copy
   up on both card variants (populate-before-connect; must never trip
   `_touched`); disabled when values equal; draft-replacement rule; 2g
   re-classification follows the new shape.
4. **Live validator pin for 5c** (dangling particle name): record what bpx
   actually reports; the app surfaces exactly that, or nothing.
Tests at minimum: command round-trip + single-entry undo (including created
ancestors), draft replacement inside the same undo step, `_touched` pin
(bare Enter never commits after docking), disabled-when-equal, ghost pull,
shape-change re-classification, hide fully gone, real-window verification
per the working agreements.

**M4 — Make main.** Clean swap + toast (3a); dirty dialog Save & switch /
Discard & switch / Cancel (3b); never-saved → Save As routing with the
default-folder rule, Cancel unwinds the switch (3c); post-swap: fresh session,
undo reset, diagnostics + pull direction follow the roles (3d). Not undoable.
*Signed design (Concept A, 2026-07-22; wireframes linked in Status).
Precondition: land the uncommitted M3 work first so this starts on a clean
tree.* As signed:
1. **Entry point**: "Make main" as a plain first button in the reference
   card's action row, beside Remove, same visual weight (the reference card
   never reads louder than the document card).
2. **Dirty prompt**: the standard message box (same anatomy as the existing
   unsaved-changes prompt): title "Unsaved changes", text "{main} has unsaved
   changes. Save before switching?", grey informative line "{ref} becomes the
   main file; {main} becomes the read-only reference.", buttons exactly
   Save & switch (default) / Discard & switch / Cancel.
3. **Toast** (existing pill): "{ref filename} is now the main file".
4. **Post-swap contract**: promoted file opens as a fresh session **from
   disk** via the normal open path (empty undo, clean dirty flag, live
   validation); demoted file **re-snapshotted from disk** (mtime, one-shot
   validation — with Discard & switch the discarded edits are never in the
   snapshot); Diagnostics reports the new main only; strip/ghosts/Copy up
   reverse automatically via the shared diff engine.
5. **Edge cases pinned**: promoted file unreadable on disk → standard
   "Cannot open file" error, swap aborts, roles unchanged; 3c Save As cancel
   or failed write unwinds the whole switch (no toast, reference stays
   docked); an uncommitted card draft belongs to the demoted session and is
   discarded with it, as on close today.
Tests at minimum: clean swap round-trip (roles, toast, undo emptied), each
dirty-dialog branch, 3c cancel unwind, discard-edits-not-in-snapshot,
diagnostics/pull direction follow roles, swap absent from the undo stack,
real-window verification per the working agreements.

**M5 — Source page.** Build per decision 13 as replaced (signed rev-4 frames
linked in Status). Scope: page widget + `</>` rail entry (enabled with any
open document), aligned raw-JSON rendering with shared section folding,
value-only highlight chips (function segments and per-table-entry included),
← gutter wired to the existing `PullParameter`/`PullSection` commands,
no-reference single-pane mode with the docking hint, ‹ › stepper, Up/Down
row navigation, double-click Editor jump, ⇄ → the full M4 flow, on-page
stale band + Reload. Explicitly out: any Workspace doorway (rejected), the
modal viewer (decision 15), difference counts on the page. Tests at minimum:
keyed alignment including gaps and shared folding; chip placement per state
(fillable ref-side chip included); ← absent on equal and main-only rows;
copy-from-page shares the undo stack (Ctrl+Z cross-page); section pull is
one undo entry; no-edit invariant (no input widgets on the page, ever);
no-reference mode renders live and re-renders on edit/undo; stepper unfold
behaviour; arrow-key row navigation; double-click jump; stale band appears
on mtime change and Reload re-snapshots; real-window verification per the
working agreements.

## 5. Risks / watch items

- The Source page (M5) renders its own aligned JSON rows — do not entangle
  it with `BpxTreeModel`; the only Editor link is the double-click jump
  through `NavigationService`.
- The inspector reference block sits next to the card commit machinery; the
  Qt pitfalls in the project guide (populate-before-connect, `_reset_draft` ordering)
  are the live hazards.
- Source page double-click semantics must not fight row selection or the ←
  gutter clicks.
- Offscreen suite cannot disprove on-screen window bugs — drive the real app
  for the new page and the swap dialogs before calling a milestone done.
