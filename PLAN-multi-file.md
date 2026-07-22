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
   raw inequality. No numeric tolerance, no semantic curve diff.
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
13. **Compare page (round 3–4)**: a separate page, enabled when a reference is
    docked. Body is **one long collapsible tree, starting fully collapsed** —
    the landing view is the structural diff. Columns: Parameter | Main | ↑ |
    Reference. Section nodes carry counts ("3 differ · 1 ref only" / "=");
    ghost sections are dashed `◇ REF ONLY` nodes with ↑ pull section. Header:
    counts, ‹ › next/prev difference (auto-expands target section), "expand
    differences", differences-only toggle, ⇄ (= Make main, full M4 flow).
    Double-click a row → Editor at that parameter via `NavigationService`.
    Rejected deliberately: sort-keys / ignore-array-order options (comparison
    semantics are fixed), raw text diff, two-way merge, green/red palette.
14. **Coexistence rules**: one diff engine; one pull command shared by Compare
    ↑ and inspector ↑ (same session, same undo stack, Ctrl+Z from either page);
    Compare owns its own scroll/selection — the only Editor link is the explicit
    double-click jump; **no input widget ever appears on the Compare page**.
15. **Big kinds**: double-click a reference table/function → small read-only
    viewer built on the grid's existing (never-yet-used) `read_only` mode.

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

**M5 — Compare page + polish.** The collapsible structural tree per decision
13, gutter ↑ invoking the M3 commands, double-click navigation, ⇄ hooked to
M4, reference-tile counts line as the doorway; read-only viewer for big kinds;
stale-reload band. Tests: landing view is collapsed structure, copy-from-page
shares the undo stack, no-edit invariant, navigation jump.

## 5. Risks / watch items

- Ghost tree nodes were cut from the Editor by the rev 3 rethink; if the
  Compare page (M5) reuses `BpxTreeModel`, its contract with navigation and
  the ⚠ refresh path is still the risk to respect.
- The inspector reference block sits next to the card commit machinery; the
  Qt pitfalls in the project guide (populate-before-connect, `_reset_draft` ordering)
  are the live hazards.
- Compare page double-click semantics must not fight row selection for ↑.
- Offscreen suite cannot disprove on-screen window bugs — drive the real app
  for the new page and the swap dialogs before calling a milestone done.
