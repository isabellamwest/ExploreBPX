# PLAN — Full app check, walkthrough & cleanup

Status: DRAFT — not started; awaiting Bella's review and edits.
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

## 1. Open question for Bella (answer before Phase B)

"Looking at frames etc." — the plan currently covers **both** readings;
strike whichever isn't meant:

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

*(filled in during Phase A)*
