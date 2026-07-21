# PLAN — Full app check, walkthrough & cleanup

> **⚠ This is a plan, not a spec — a proposal that can change, not a locked
> requirement.** Where it and the running app differ, the app is correct. Read it
> as context, not a mandate to implement verbatim; re-check against the code and
> confirm with Bella before acting on anything still open.

Status: Phase A COMPLETE 2026-07-21 (baseline green, §7 checklist built,
§1 answered: both readings). Awaiting Bella's sign-off to start Phase B.
Purpose: a human end-to-end run of the real app (never done since the
completion track landed), a friction log of awkward parts, then a
triaged cleanup/optimisation pass. Discovery first, fixes second —
nothing gets changed during the walk itself.

## 0. Working agreements (same as previous tracks)

- One phase at a time; STOP for sign-off before moving on and before every commit.
- No pushes, ever. Commit messages short and simple, no AI trailer.
- Validator fidelity and layer boundaries are non-negotiable; `test_boundaries.py` stays green.
- Any UI change that comes out of triage goes through the 3-concept design workflow.
- Headless green is *not* proof for on-screen behaviour (see pitfalls, §6).

## 1. Open question for Bella — ANSWERED 2026-07-21: cover both

"Looking at frames etc." covers **both** readings; the walk checks both:

- **Visual frames**: QFrame borders, card outlines, spacing, alignment,
  layout jumps on resize, dark/light inconsistencies.
- **Frame pacing / responsiveness**: repaint storms, lag while typing in
  table cells, slow section switches, startup time.

## 2. Phase A — Baseline & checklist (no app changes)

- Run `python -m pytest` from the repo root; record the honest baseline
  (matplotlib is known-missing from the `.venv` — note, don't hide).
- Build the walkthrough checklist from the *running app's* surface, not docs:
  sections and page buckets, the six parameter kinds (scalar, integer, enum,
  function, table, unknown), custom sections + typed custom parameters
  (rename / move / duplicate), the validation page (Outstanding section,
  experiment card, badge), example library, open/save/export paths.
- Output: the checklist appended to this file as §7 before the walk starts.

## 3. Phase B — Human end-to-end walk (real app, on-screen)

Real Windows platform via `/run` — **not** offscreen. If any step needs
automation, use the QEvent.Show-filter technique from the memory notes.

Core authoring loop, in order:
1. New document → add sections → add parameters of every kind.
2. Fill values: typing, paste card, CSV import, function/table editing, undo/redo chains.
3. Custom sections and custom parameters: create, type, rename, move, duplicate.
4. Completion: "fields to add" group, set-model action, completion badge behaviour.
5. Validate → read diagnostics → fix an error → re-validate.
6. Save → reload → re-validate → confirm round-trip fidelity.

Supplementary passes:
- Open both shipped examples (About:Energy NMC, LFP) and one deliberately broken file.
- Legacy-file auto-convert (pre-1.1.1 State handling).
- Keyboard-only pass (focus order, Delete, Enter-commit semantics).
- Resize/maximise/restore; multi-section navigation while a card is mid-edit.
- Watch throughout for the §1 "frames" concerns.

Rules: log, don't fix. Output: `WALK-friction-log.md` — numbered entries with
severity (bug / awkward / cosmetic / perf / dead-code-suspect), repro steps,
screenshots where visual.

## 4. Phase C — Triage & sign-off

- Classify the friction log; propose priorities and rough cost per item.
- Bella picks what gets fixed; everything else is explicitly parked in the log.
- Split accepted work into: bug fixes, UX changes (design workflow), cleanup, perf.

## 5. Phase D — Cleanup & optimisation (only what triage approved)

Cleanup sweep (small, test-backed steps, one concern per commit):
- Dead code: unused imports/functions, unreachable branches, leftover
  scaffolding from the input-system and completion redesigns.
- Duplicated logic across cards (`app/ui_qt/cards/` is the biggest surface —
  ~30 modules; check base/registry patterns are actually shared).
- Anything the walk flagged as dead-code-suspect.

Optimisation — **measured only**:
- Profile before touching anything (startup, large-file open, table editing,
  validation run). Fix only measured hotspots; record before/after numbers.

## 6. Phase E — Final verify, docs, memory

- Full suite + a targeted on-screen re-walk of every flow that changed.
- Sync `docs/` where the walk proved them stale (they are reference, not spec).
- Update memory notes; settle any PLAN amendments owed (bpx 1.1.1 note exists).

## Pitfalls carried forward

- Offscreen suite cannot disprove native-window bugs — the whole point of Phase B.
- `QMenu.exec()` blocks for real; use the `QTimer.singleShot` + `activePopupWidget()` idiom.
- Cards populate widgets *before* connecting change signals; `_reset_draft`
  clears `_touched` after `reset()`.
- Two `PyparsingDeprecationWarning`s from `bpx` are expected noise.

## 7. Walkthrough checklist

*Built 2026-07-21 from the running app's surface (code-derived, not docs).*

### Phase A baseline (recorded)

- `python -m pytest`: **1249 passed, 0 failed, 0 skipped, 47 warnings, 55s.**
  The two expected bpx `PyparsingDeprecationWarning`s present. matplotlib
  absence cost nothing (no skips).
- Deprecation warnings noted for triage: `QTableWidgetItem.setTextAlignment(int)`
  in `app/ui_qt/cards/csv_dialog.py:244`; `QApplication.setActiveWindow` in
  `tests/test_undo.py:558`.

### Plan corrections found while building this list

- There is **no menu bar** — no "Open example" menu path exists. The bundled
  examples' only in-app entry is **Compare…** on the experiment card; opening
  them as documents means Open File… → `app/data/example_documents/`.
- "Legacy auto-convert" is **upstream bpx behaviour**, not app code. The LFP
  example ships in legacy BPX 0.1 shape and `bpx` converts it on load (see
  `app/data/example_documents/about_energy/NOTICE.md`); the walk checks the
  conversion warning is surfaced faithfully, not an app feature.
- Naming drift for triage: activity bar says **Diagnostics**, but
  `core/page_buckets.py` docstrings call it "the Validation page". Cosmetic.

### A. Startup & Workspace page

- [ ] Cold start: time to window; Workspace page is the landing page with no document.
- [ ] Document info card absent/empty state correct; New buttons (SPM / SPMe / DFN / Partial) present.
- [ ] Open File… (json/yaml/yml filter); drag-and-drop a BPX file onto the page.
- [ ] Dirty-guard QMessageBox (Save / Discard / Cancel) when opening over unsaved changes.
- [ ] Status bar shows `<filename> | Modified/Saved` correctly through the above.

### B. New document & tree structure

- [ ] New SPM scaffold: tree shows Header / Parameterisation children; State & Validation absent until added.
- [ ] Right-click empty tree space → Add section ▸ (root-level State / Validation — only path to them).
- [ ] Add material… on Particle containers; Add experiment… on Validation (NamePopup anchors under row).
- [ ] Add subsection… inside User-defined; nested free-form sections render with "· custom" suffix.
- [ ] Rename… only offered on user-named keys; Remove asks for confirmation only when target non-empty.
- [ ] Tree ⚠ marker appears/clears as descendant errors come and go.

### C. Parameter kinds — one of each, all affordances

- [ ] **Scalar**: type value; unit label; Enter commits, Escape reverts; validity badge updates.
- [ ] **Integer**: spinbox stepping; fallback to free text when stored value isn't a valid int.
- [ ] **Enum**: pick from opened popup = immediate commit; arrow-step on closed combo = draft until Enter.
- [ ] **Boolean**: checkbox click commits immediately.
- [ ] **Text**: multiline growth; Shift+Enter newline vs Enter commit.
- [ ] **Function**: all mode-strip modes (FloatInt / Function / InterpolatedTable / Raw when present);
      expression syntax hint; x/y grid + live plot updates.
- [ ] **Map**: FloatInt vs per-material dict; known-materials add-menu; Raw mode.
- [ ] **Table / Series**: type-to-edit cells; +/− rows; paste (Ctrl+V and right-click) with
      Replace/Append preview; Import CSV… mapping dialog (never auto-applies); Expand takes over
      Inspector; cell-level validator tinting.
- [ ] **Unknown/Raw**: lenient parsing round-trips; ragged table falls back to RawValueCard.
- [ ] Undo/redo chains across several of the above, including mid-draft focus rules
      (undo never bypasses an uncommitted edit).

### D. Custom parameters

- [ ] "+ Add parameter" popup: Suggested (blue) vs Other groups; type-to-filter; keyboard nav
      (Down/Up/Enter, staged Escape).
- [ ] "Create custom parameter…" footer: Name/Unit/type picker (Scalar/Text/Boolean/Table/Series).
- [ ] Row context menu: Rename… (inline pencil row), Duplicate, Move up/down (disabled at ends),
      Remove parameter; Delete key on list row.
- [ ] Rename/duplicate gating: schema-declared params not renameable; Particle names are bpx
      reference targets (rename propagates or is blocked — observe which, faithfully).

### E. Completion

- [ ] "▸ N fields to add" group: collapsed by default, per-section toggle, "+" adds with empty seed.
- [ ] Suppressed for undeclared model except in Header.
- [ ] DECLARE_MODEL Outstanding task → Choose… navigates to Header.Model; committing model
      auto-adds required sections in one undo step.
- [ ] Diagnostics badge (red/amber count) tracks errors/outstanding live.

### F. Diagnostics page

- [ ] Summary chips (errors / warnings / outstanding) + text filter are view-only.
- [ ] Rail: All sections + per-bucket entries, quiet badges, arrow-key selection.
- [ ] Detail: Issues + Outstanding group-boxes; "OPTIONAL — K UNFILLED" subgroup.
- [ ] Row activation (Enter/double-click) navigates; action labels "Go to ›" / "+ Add section" /
      "Choose…" match task kind.
- [ ] Fix an error in the editor → re-validate → diagnostic clears everywhere (badge, tree ⚠, card).

### G. Validation runs & Compare…

- [ ] ValidationEmptyState: "+ Add experiment" and "Import CSV as new experiment…".
- [ ] ExperimentCard: 4-column grid, CSV drop-zone (only while run empty), header import button.
- [ ] Compare…: bundled NMC/LFP samples grouped by cell; user-file refs; "Open BPX file…";
      chip legend removal; Chart/Table toggle; strictly read-only (document untouched after close).

### H. File round-trip

- [ ] Save (existing file) vs Save-As prompt (new doc); Export always prompts, never clears dirty.
- [ ] Save → reload → re-validate: identical diagnostics, values, custom sections/params, key order
      sanity.
- [ ] YAML open path (not just JSON).

### I. Examples, broken & legacy files

- [ ] Open `nmc_pouch_cell.json` (modern shape) as a document — clean validate expected.
- [ ] Open `lfp_18650_cell.json` (legacy BPX 0.1) — bpx auto-convert happens; its conversion
      warning surfaces faithfully in Diagnostics.
- [ ] Open a deliberately broken file (bad type, unknown field, malformed JSON) — errors shown
      faithfully, app stays usable.

### J. Keyboard-only pass

- [ ] Tab/focus order across the three panes; search (Ctrl+F/Ctrl+P, Up/Down cycle, staged Escape).
- [ ] Delete only acts on parameter-list rows (tree unaffected); Ctrl+Z/Ctrl+Shift+Z focus-aware.
- [ ] A full add-section → add-param → fill-value → validate loop without touching the mouse.

### K. Frames watch-list (both readings, per §1)

Visual, throughout every step above:
- [ ] Card outlines/QFrame borders consistent; spacing/alignment on all card kinds.
- [ ] Resize/maximise/restore: layout jumps, splitter behaviour, Expand-mode reflow.
- [ ] Elided toolbar identity label; badge rendering at 0/1/many counts.

Pacing/perf, measured where suspicious:
- [ ] Startup time; large-file open (biggest example); typing latency in table cells.
- [ ] Section switches with grids/plots mounted; validation-run repaint behaviour.
- [ ] Watch for repaint storms while dragging splitters or resizing with plots visible.
