# PLAN — Workspaces: the settled model

## Status (2026-08-09): shipped, all five phases

Implemented at Isabella's instruction in seven commits: `4951f31` Phase 1
(store), `7b3f57b` Phase 2 (app wiring), `0ed7815` Phase 3 (rail + board),
`b46147a` Phase 4 (launch), `15733fb` fixes found by driving the real page,
`204d74c` Phase 5 (docs) + the v1-migration change, `55fd363` a docstring
tidy. Suite: 6 failed / 1867 passed, the same six environmental failures as
the pre-work baseline (real-modal-dialog and keyboard-focus tests needing a
window manager — note that the project guide's "2 pre-existing failures" is stale).

Design record: design archive entry "Workspaces — the settled model"
((internal design archive), private —
this file is the authoritative, agent-readable copy). Fourth pass; supersedes
"Sets — the rethink" and the earlier workspace-page proposals.

**The model below is what shipped**, with four deliberate departures:

1. **An ordinary open never rewrites a *named* workspace** (Isabella's call,
   against the edge rule below). Naming is the act that says "stop rewriting
   this", so opening a file beside a named workspace starts a fresh untitled
   one carrying the still-pinned references, and leaves the named entry
   alone. Untitled workspaces still swap their main in place as written.
   Reopening the same main in the same mode is not a swap at all.
2. **A reference slot's record opens beneath the board** (Isabella's call —
   the plan never said where the existing per-reference record went). The
   panel names which reference it is showing and carries the Read-only tag
   once, rather than four times on the board.
3. **`duplicate()` of a *named* workspace makes a named copy** ("study
   copy", uniquified) rather than an untitled one: a fork of something
   deliberately kept should be equally safe. Untitled workspaces fork to
   untitled entries as written.
4. **The v1 migration makes the old last-workspace current**, so the first
   launch after an upgrade hands back what was open. That slot meant exactly
   "what you had open", which is the question `current_id` now answers.
   Verified against a real v1 store on disk.

Two smaller notes: `test_store_never_contains_content_or_verdicts` kept its
intent but its key allowlist grew (`id`, `recent_workspaces`, `current_id`) —
"untouched" was not literally possible. And Phases 1 and 2 are separate
commits with a red tree between them; shims faking the old overwrite
semantics would have lied about behaviour that was being deleted.

Phase 3's open question is answered: the per-reference differ count **was**
already computed (`ComparisonResult.differ_count`) and shown nowhere but a
strip tooltip. It is now the "N values differ ▸" route.

## The model

A **workspace** is the files you work with together — one editable main document
plus up to four read-only references (`MAX_PINNED_REFERENCES = 4`,
[app/state/app_state.py](app/state/app_state.py)).

1. Opening a file **starts** a workspace. It is untitled until named. (A scaffold
   document joins its workspace only once saved to disk — no path before that;
   matches existing behaviour in `tests/test_app_state_history.py`.)
2. Switching away **shelves** an untitled workspace under **Recent** (cap 8,
   newest first, oldest falls off, content-duplicate entries merged). Nothing is
   discarded by a click; there is no "Name it first?" prompt.
3. **Naming keeps it for good** — it moves from Recent to Workspaces and never
   decays. Naming is a promotion, not a rescue.
4. A workspace **looks after itself**: live identity, not snapshot. Add/remove a
   reference or swap the main and the record updates in place. No save button,
   no "changed since saved", no replace confirmation. **This deliberately
   reverses today's tested snapshot semantics**
   (`test_named_workspaces_are_snapshots_not_live`) — sign-off item 1.
5. A workspace remembers **where** files are (paths only, never content —
   preserve `test_store_never_contains_content_or_verdicts`). Missing files are
   named, offered **Locate… / Remove**, and the rest opens anyway.

Identity is an internal **id** (new field), not the main's path — identity
survives a main swap.

## What gets deleted

Shipped today, removed by this design:
- "Save current workspace as…" button and the save/rename/replace/remove dialog
  flow in `main_window.py` (`_on_workspace_save` etc.); replaced by name-unique
  keep/rename via the existing `_ask_workspace_name` dialog.
- "Replace workspace 'Foo'?" confirm (re-saving stops existing).
- Snapshot semantics for named workspaces (become live).
- "Resume last workspace" row (subsumed: top row of Recent, no longer vanishes
  once something is open).
- Recent **files** rows in the rail (subsumed by Recent workspaces; recent files
  stay in the store to feed the ＋ menu).
- Hidden-when-empty rail groups (Workspaces and Recent become always visible,
  with one-line empty-state copy naming the concept).

Never build (pass-2/3 proposals now obsolete): "changed since saved" pill,
"Name it first?" prompt, ⋯ context menus (the app's idiom is hover-revealed row
actions — `_HistoryRow.add_hover_action` in
[app/ui_qt/workspace_panel.py](app/ui_qt/workspace_panel.py)).

## Edge rules (decided, not open)

| Situation | Behaviour |
|---|---|
| Open a file while a workspace is active | Swaps into the Main slot of the **current** workspace; references stay; id survives. A separate line of work = **New workspace** (shelves the untitled one, clears the board). |
| Unsaved file edits on switch/close/reopen | Existing discard guard (`_confirm_discard_if_dirty`) runs first, unchanged. The workspace itself never blocks — it has nothing to save. |
| Two Recent entries with identical main+refs | Older merged into newer (newest wins, like recent-files dedup). Different refs = different arrangements, both stay. |
| Naming with a name in use | Inline "that name is in use"; never overwrite. Names unique; identity is the id. |
| Same file as main and reference | Stays blocked (existing `IS_MAIN` outcome). Same file in many workspaces is fine. |
| Missing main at open | Open what's there: empty Main slot + references + banner with Locate…/Remove. (Today it refuses entirely — change that.) Locate… repoints the stored path and is the only path-edit that exists. |
| History file corrupt / newer schema | Announce and start clean; never block launch (existing `load_failed` behaviour, keep). |
| Launch | Reopens the current workspace (named or not), honouring recorded D3 open modes (`normal`/`read_only`/`converted_copy`). Today nothing reopens — change that. |

## UI (signed wireframes live in the artifact)

- Page keeps the name **Workspace**; header carries the workspace's own name
  (click-to-rename). Vocabulary settled: the app says "workspace"; the library's
  "parameter set" is untouched (field vocabulary — validator-fidelity spirit).
- **Rail**: Workspaces group (named, forever) above Recent (unnamed, last 8).
  Rows: existing `_HistoryRow` chips + glyph (main bar + 4 ref dots), "open now"
  pill on the current one, hover actions Name / Rename / Duplicate / Remove /
  Locate…. "New workspace" button. No Save-as, no Resume row, no recent-file rows.
- **Board** (replaces the two stacked `TintedSection`s in `_build_pane`): main
  card ⇄ four reference slots inside a "This workspace" frame. Empty slots carry
  ＋ → one menu, three routes: reference library / open a file / recent files.
  At cap the ＋ simply isn't there (slots are the drawn cap; drop the "n of 4
  pinned" counter and the two dock buttons).
- **Routes out** (page must not be a dead end): "Edit its parameters ▸" → Editor;
  "N errors · why? ▸" → Diagnostics; "N differ ▸" per reference → Source diff
  against that reference. **Verify during Phase 3**: pass three claimed the
  per-reference differ-count is already computed and shown nowhere — confirm; if
  not, computing it is part of Phase 3, not a reason to drop the route.
- **Strip** below the board: existing identity editing (Title/Description/
  Citation → `SetValue`) and the fact plaque, re-housed unchanged.

## Implementation phases (each lands green on its own)

Layer boundary: all Phase 1–2 work stays Qt-free in `app/state/`
(`tests/test_boundaries.py` guards); everything visual in `app/ui_qt/`.

**Phase 1 — state, the store** ([app/state/workspace_history.py](app/state/workspace_history.py))
- `WorkspaceRecord` gains `id`; `last_workspace` (single slot) →
  `recent_workspaces: list` (cap 8, dedup-on-shelve). `SCHEMA_VERSION` → 2 with
  migration (old last-workspace becomes first Recent entry; named carry over).
- Live identity: today's `set_last_workspace` sync becomes update-current-record-
  in-place, named or not. Replace `save_named` overwrite semantics with
  name-unique `keep / rename / remove / duplicate / relocate`.
- Tests: invert `test_named_workspaces_are_snapshots_not_live` to a live-update
  test; add migration, dedup-on-shelve, cap-decay, relocate. Keep the
  pointers-only test untouched.

**Phase 2 — state, app wiring** ([app/state/app_state.py](app/state/app_state.py))
- Track current workspace id; open-while-active swaps main in place; New
  workspace shelves + clears; switching shelves the untitled one. Preserve
  scaffold/new-from-file semantics (existing tests in
  `tests/test_app_state_history.py`).
- `add_recent` (recent files) recording stays — feeds the ＋ menu instead of the rail.

**Phase 3 — ui, rail + board** ([app/ui_qt/workspace_panel.py](app/ui_qt/workspace_panel.py), [app/ui_qt/main_window.py](app/ui_qt/main_window.py))
- Rail rebuild per UI section above; delete `_on_workspace_save` / replace-confirm
  path; keep `_ask_workspace_name` for naming/renaming.
- Board rebuild per UI section above; wire the three routes out.
- Largest test delta: `tests/test_workspace_panel.py` layout assertions and
  `tests/test_workspace_history_ui.py` save/replace flows rewritten to the model.

**Phase 4 — ui, launch**
- Auto-reopen current workspace at startup (through `_restore_workspace`,
  honouring D3 modes via `_open_recorded_main`); missing main degrades to
  banner + Locate instead of refusing; broken history announces and starts clean.

**Phase 5 — docs + proof**
- Rewrite `docs/architecture.md` Workspace section (stale twice over: still
  "one Primary + one Reference", no history/rail); prune landed items from
  `docs/future.md`.
- Full headless suite vs the known baseline (matplotlib missing from .venv,
  2 pre-existing failures); then drive the real app and screenshot the five
  workflow steps against the artifact wireframes, reporting divergences honestly.

## Sign-offs (all given, 2026-08-09)

1. **Live-identity trade (rule 4)** — the one real loss: no snapshot to
   experiment against; `Duplicate` on the hovered row is the fork escape hatch.
   Reverses shipped, tested behaviour. *Given* — and softened by departure 1
   above, which stops an ordinary open from rewriting a named workspace.
2. **Name stays "Workspace"** (vs "set"/"study" — rejected for the parameter-set
   collision and grandiosity respectively). *Given.*
3. **Go on Phase 1.** *Given — implemented through Phase 5.*

Settled, not to re-litigate without Isabella's say-so: the board, "This
workspace" on the frame, Title/Description/Citation in the strip, Close and
Empty, the ＋ menu, storage with the app (not files on disk), Recent replacing
discard-on-switch, hover actions replacing ⋯ menus, launch reopen, Locate…
alongside Remove.
