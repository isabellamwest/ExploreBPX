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
4. **Ghost treatment is loud, everywhere**: blue dashed border + blue tint +
   italic value + `◇ REF ONLY` tag. Ghost-selected inspector card is headed
   "Not in the main file" and offers only ↑ Copy up.
5. **↑ Copy up** (the only mutation): verbatim copy reference → main. Destination
   exists → set; missing → add; missing ancestors → created in the same command.
   **One undo entry** always. Section pull = one batch entry. Copy up commits
   immediately and replaces any uncommitted card draft (undoable). Same-key
   different-shape copies verbatim; row + card re-classify from the new shape.
   One-way only — the reference is never a target.
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
12. **Editor comparison (Concept 1)**: tree gets per-section difference counts
    (text-append, like the ⚠ marker) + dashed ghost nodes; parameter list gets
    row states inline + ghost rows + differences-only filter + comparison strip
    (ref name, counts, prev/next, hide); inspector gets the reference block
    under the editing card (main value above, reference below, ↑ Copy up).
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

**M2 — diff engine + comparison-aware Editor.** `app/core/compare.py` (pure
core): keyed matching, per-kind raw equality, per-section counts, ghost
sections; order-independence and 2h asymmetry pinned by unit tests. UI: list
row tints + ghost rows + differences-only filter + comparison strip; tree
counts + ghost nodes. Recompute lazily (visible section + counts) on document
change.

**M3 — ↑ Copy up + inspector reference block.** Core commands `pull_parameter`
/ `pull_section` (verbatim, ancestor-creating, one undo entry each). Inspector
reference block (populate-before-connect; must never trip `_touched`);
ghost-card variant; draft-replacement rule; 2g re-classification. **Live
validator pin for 5c** (dangling particle name): record what bpx actually
reports; the app surfaces exactly that.

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

- Ghost tree nodes (M2) touch `BpxTreeModel`'s contract with navigation and
  the ⚠ refresh path — do this deliberately, not as a bolt-on.
- The inspector reference block sits next to the card commit machinery; the
  Qt pitfalls in the project guide (populate-before-connect, `_reset_draft` ordering)
  are the live hazards.
- Compare page double-click semantics must not fight row selection for ↑.
- Offscreen suite cannot disprove on-screen window bugs — drive the real app
  for the new page and the swap dialogs before calling a milestone done.
