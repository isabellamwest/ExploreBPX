# PLAN — UI wording pass

**Status:** approved by Bella 2026-08-10, **not implemented**. No code touched.
**Scope:** wording only. No layout, no behaviour, no new controls — except the
one small addition in W2 (a heading label), which is approved.

Every target below was located by grep at authoring time; line numbers are from
the tree at commit `c03ec86` and are **hints** — match on the quoted string, not
the number. All strings are exact, including the `·` (U+00B7), `▸` (U+25B8) and
`›` (U+203A) characters and the `…` ellipsis.

Do these in one pass, then run `python -m pytest` from the repo root and fix the
test fallout listed at the bottom (it is enumerated, not guessed).

---

## 1. Workspace page

### W1 — current-workspace pill *(approved)*

`app/ui_qt/workspace_panel.py:1590`

```
"open now"   ->   "Open"
```

Why: it read as a command, not a state, and it sits on the one row built
`clickable=False` (`_HistoryRow(clickable=not entry.is_current)`, ~:1573), so it
invited a click that does nothing.

There is a comment at `app/ui_qt/main_window.py:2202` that quotes `"open now"` —
update the quotation so the comment still matches the code.

### W2 — make "workspace" vs "file" unmissable *(approved, Bella's wording: "ensure it's so obviously clear what is a workspace, and what is a file")*

The Workspace page currently shows **three** lists whose nouns are not all
stated. Two are workspaces, one is files, and the word "Recent" is used for
both. Fix: **every list on this page names its noun.**

| Where | File:line | Current | New |
|---|---|---|---|
| Rail group 1 (named workspaces) | `workspace_panel.py:1510` | `Workspaces` | `Named workspaces` |
| Rail group 2 (unnamed workspaces) | `workspace_panel.py:1515` | `Recent` | `Recent workspaces` |
| Start surface, recent-file rows | `workspace_panel.py:~1303-1309` | *(no heading)* | add `Recent files` |
| Board ＋ menu submenu | `workspace_panel.py:~1830` | `Recent files` | unchanged — already correct |

Confirmed semantics (do not re-derive): the rail's first group is
`history.workspaces` = **named** workspaces; the second is
`history.recent_workspaces` = **unnamed** ones, evicted by recency
(`main_window.py:~2226-2230`). Naming a workspace promotes it between the two
(`main_window.py:_on_workspace_name`). So the old `Workspaces` heading sat over
only *some* workspaces — `Named workspaces` is both clearer and more truthful.

Rail width is 340px (`_RAIL_WIDTH`) and headings render through
`typography.panel_title` at MICRO/caps, so `NAMED WORKSPACES` and
`RECENT WORKSPACES` both fit comfortably.

**The `Recent files` heading — implementation detail that matters:** the start
surface hides its recent block whole when there are no rows
(`self._recent_host.hide()`, and `set_recent_files` ends with
`self._recent_host.setVisible(bool(self._recent_rows))`). The new label must
therefore live **inside** `_recent_layout` / `_recent_host`, not as a sibling in
the outer layout, or an empty start surface will show a heading over nothing.
Style it like its two peers on that surface: `QLabel` with
`setObjectName("BoardSlotRole")`, same as `Main` (~:1292) and `New document`
(~:1311). Result reads: **Main → Open a file… → Recent files → New document.**

### W3 — main card edit route *(approved)*

`app/ui_qt/workspace_panel.py:903`

```
"Edit its parameters ▸"   ->   "Edit ▸"
```

Also update the class docstring at `workspace_panel.py:845`, which quotes both
route labels.

### W4 — main card diagnostics route *(approved)*

`app/ui_qt/workspace_panel.py:951`

```
f"{errors} error{plural} · why? ▸"   ->   "Diagnostics ▸"
```

Keep the button and its `if errors:` visibility gate exactly as they are — this
is the board's only route to Diagnostics, so it stays; only the label changes.

Two reasons the old label was the messiest text in the app: it **repeated** the
count already shown by the validity badge directly above it in the same card
(`self._badge.setText(validity)`, where validity is `"2 errors, 1 warning"`),
and its lowercase `why?` clashed with the sentence-case `Edit ▸` beside it.
`Diagnostics ▸` is a destination noun that pairs with `Edit ▸`.

The `plural` local at ~:950 becomes unused — remove it.

### W5 — Locate… tooltip *(approved)*

`app/ui_qt/workspace_panel.py:1193`

```
"Point this workspace at where the file is now"   ->   "Find where the file moved to"
```

---

## 2. Stale nouns

### S1 *(approved)* — `app/ui_qt/editor_page.py:17`

```
"No document open - use the Workspace tab to open or create one"
->
"No document open - open or create one on the Workspace page"
```

Workspace is a rail page, not a tab.

### S2 *(approved)* — `app/ui_qt/parameter_info_popover.py:89`

```
"Full description in the Documentation tab."
->
"Full description in the Documentation section."
```

Verified: Documentation is a collapsible **section** in the Inspector
(`inspector.py:~153`, `collapsible=True`). Three code comments also say "tab" —
`parameter_info_popover.py:27`, `latex.py:54`, `core/parameter_metadata.py:32`.
Fix those comments too so the vocabulary is consistent in the source.

---

## 3. One state, one spelling

### C1 *(approved)* — grid pending bar, `app/ui_qt/cards/grid.py:393`

```
"Unsaved edits"   ->   "Unsaved changes"
```

Matches the status bar, the record plaque and the unsaved-changes dialog.
Docstrings/comments quoting `"Unsaved edits"` should follow:
`cards/grid.py:33,733,1218`, `cards/base.py:217`, `cards/bodies.py:76`,
`cards/modal.py:127`, `cards/experiment.py:350,455`.

### C3 *(approved)* — pin toasts, `app/ui_qt/main_window.py:1566`

```
f"{self._state.references[-1].filename} · pinned as reference"
->
f"Pinned {self._state.references[-1].filename} as reference"
```

so the library path matches the file path at `main_window.py:1523`
(`f"Pinned {…} as reference"`). Identical outcome, identical sentence.
Leave `"Already pinned as reference"` (`:1524`, `:1568`) alone.

### C4 *(approved)* — error dialog titles

| File:line | Current | New |
|---|---|---|
| `main_window.py:1869` | `Save failed` | `Cannot save` |
| `main_window.py:1947` | `Save failed` | `Cannot save` |
| `main_window.py:2080` | `Export failed` | `Cannot export` |

`Cannot open file` (`main_window.py:1081, 1207, 1520, 1562, 1686`) and
`Cannot save` (`:1897`) already use the settled form — leave them.

### C5 *(approved)* — open-dialog window titles

| File:line | Current | New |
|---|---|---|
| `main_window.py:1066` | `Open BPX` | `Open BPX file` |
| `main_window.py:1504` | `Open BPX` | `Open BPX file` |

`cards/database_examples_dialog.py:607` already says `Open BPX file` — leave it.
Menu items keep their `…`: `Open a BPX file…` (`workspace_panel.py:~1823`) and
`Open a file…` (`workspace_panel.py:1297`) are actions, not window titles, and
stay as they are.

---

## 4. Labels and tooltips that restate themselves

### D1 *(approved)* — grid pending buttons, `app/ui_qt/cards/grid.py:399-408`

```
label   "Apply (Enter)"                   ->  "Apply"
tooltip "Write these edits to the file"   ->  "Write these edits to the file (Enter)"
label   "Discard (Esc)"                   ->  "Discard"
tooltip "Revert to the file's value"      ->  "Revert to the file's value (Esc)"
```

The keys move into the tooltips; they are not lost. Leave the accessible names
(`Apply edits` / `Discard edits`) as they are.

### D3 *(approved)* — reference ledger pull button, `app/ui_qt/cards/reference_block.py:216,219`

```
label   "Use this value"                          ->  "Use"
tooltip f"Use this value from {…name}"            ->  f"Use the value from {…name}"
```

Comments quoting `"Use this value"` at `reference_block.py:145,248`,
`ghost_card.py:7,87`, `parameter_card.py:113` and the QSS comment at
`style.py:657` should be updated to match.

### D4 *(approved)* — `app/ui_qt/cards/experiment.py:259`

```
"Compare this run's data against sample cells or another BPX file"
->
"Compare against other runs"
```

### D5 *(approved)* — `app/ui_qt/cards/database_examples_dialog.py:460`

```
"Add the validation runs of another BPX file to this comparison"
->
"Add another file's runs"
```

---

## 5. Consistency

### E1 *(approved)* — `app/ui_qt/diagnostics_panel.py:125`

```
_ACTION_GO_TO = "Go to ›"   ->   _ACTION_GO_TO = "Go to ▸"
```

`▸` (U+25B8) is the app's right-chevron everywhere else (workspace routes, fold
headers, source page, parameter list, hint blocks). `›` (U+203A) was the lone
exception. Comments quoting it: `diagnostics_panel.py:730`,
`parameter_list.py:470`, `parameter_row.py:386`.

### E2 *(approved)* — status bar separator, `app/ui_qt/main_window.py:~2103`

```
f"{name}  |  {state_text}"   ->   f"{name} · {state_text}"
```

`·` is the separator the whole app uses.

---

## 6. Explicitly REJECTED — do not implement, do not re-propose

| Item | Decision |
|---|---|
| `Remove` banner tooltip `Forget this file (the file itself is not touched)` | **Keep as is.** Bella's call. |
| Inspector verdict badge `Invalid` → `{n} errors` | **Keep `Invalid`.** Bella's call. |
| `Create custom parameter "{typed}"` → `Create "{typed}"` | **Keep as is.** Bella's call. |
| En dash in chart legend tooltip `domain {min} – {max}` (`cards/table_preview.py:308`) | Out of scope. Bella: "don't care". Leave it. |
| `Active file` → `Main` in the Compare dialog | Not approved. Leave it. |
| Unifying `incomplete` / `remaining` / `to add` / `unfilled` | Out of scope — each sits in a different grammatical slot. |
| Unifying the four senses of `Remove` (unpin / forget / delete workspace / destroy content) | Out of scope — that is a design change, not a wording fix. |

Also confirmed by codepoint scan: **there are no em dashes (U+2014) anywhere in
`app/ui_qt/`**. The layer already uses a spaced hyphen for breaks. Nothing to do.

---

## 7. Test fallout — these WILL fail until updated

Enumerated by grepping `tests/` for the affected strings. Update the assertion,
not the app, in every case below.

**`tests/ui_driver.py`** (fix first — the suite reads the app through it):
- `:850` docstring quotes `"open now"` → W1
- `:854` finds the pill by `objectName="HistoryRowPill"` — **object name is
  unchanged, so this keeps working.** Only the docstring needs a touch.
- `:918` `groups = {"Workspaces": ws._workspaces_group, "Recent": ws._recent_group}`
  → W2. The dict keys are the group *titles*; update both to
  `"Named workspaces"` / `"Recent workspaces"`, and check every caller of
  `visible_rail_groups()` (or whatever it is named) for hard-coded `"Recent"`.
- `:986` docstring quotes `"Edit its parameters ▸"` → W3
- `:993` docstring quotes `"N errors · why? ▸"` → W4

**Assertions that break:**
- `tests/test_workspace_history_ui.py:469` — `d.issue_route_text() == "1 error · why? ▸"` → `"Diagnostics ▸"` (W4)
- `tests/test_workspace_panel.py:196` — same assertion → `"Diagnostics ▸"` (W4)
- `tests/test_grid_pending.py:83` — `apply_button.text() == "Apply (Enter)"` → `"Apply"` (D1)
- `tests/test_grid_pending.py:84` — `discard_button.text() == "Discard (Esc)"` → `"Discard"` (D1)
- `tests/test_grid_pending.py:9` — module docstring says `"Unsaved edits" bar` → C1
- `tests/test_parameter_info_popover.py:94` — `any("Documentation tab" in t …)` → `"Documentation section"` (S2)
- `tests/test_reference_library_flow.py:64` — `d.toast_text() == f"{entry.short_title} · pinned as reference"` → `f"Pinned {entry.short_title} as reference"` (C3)
- `tests/test_validation_page_layout.py:815` — `ACTION_ROLE == "Go to ›"` → `"Go to ▸"` (E1)
- `tests/test_validation_page_layout.py:819` — `"· Go to ›" not in …` → `"· Go to ▸"` (E1)
- `tests/test_save_interventions.py:401` — asserts alert title `"Cannot save"`; this is the *stale-on-disk* dialog at `main_window.py:1897`, which is **unchanged** by C4. Re-run to confirm it still passes; if a `Save failed` path is asserted anywhere, it becomes `Cannot save`.

**Likely-but-unconfirmed, check while running:**
- `tests/test_validation_page_layout.py:129,806` — comments quoting `Go to ›`
- `tests/test_diagnostics_filters.py:426` — comment quoting `Go to ›`
- `tests/test_parameter_descriptions.py:1` — docstring says "Documentation tab"
- `tests/test_database_examples_dialog.py:483` — comment quoting `Open BPX file…`
- Any test asserting rail group titles or the start surface's child count (the
  `Recent files` label in W2 adds one widget to `_recent_host`).
- `tests/test_empty_state.py:45` asserts `"No document open"` for the
  *validation* placeholder (`diagnostics_panel.py:109`) — **not** the editor
  one. S1 does not touch it.

**Guard tests to keep green:** `tests/test_boundaries.py` (no UI imports moving
inward) and `tests/test_typography.py` (no font literals in `app/ui_qt/`).
Neither should be affected by a wording-only change, but W2 adds a `QLabel` —
give it `setObjectName("BoardSlotRole")` and let it inherit its size; do not
set a font on it.

---

## 8. Done means

1. `python -m pytest` from the repo root, green against the Windows baseline
   (on Windows the suite runs clean; report honestly if it does not).
2. Drive the real app (`/run`) and eyeball the Workspace page: rail headings,
   the `Open` pill, `Edit ▸` / `Diagnostics ▸`, and the start surface reading
   Main → Open a file… → Recent files → New document.
3. Delete this file, per the standing plan-file convention.
4. Stop before committing and offer a subject line (~50 chars, imperative, no
   body, no trailer). Suggested: `say plainly what is a workspace and what is a file`
   — trim to fit if it runs long.
