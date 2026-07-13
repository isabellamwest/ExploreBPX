# PLAN — Input system, Phases 4a → 6

> **Status: complete.** Every phase below (4a → 6) has landed. This file is kept as
> the record of the verified facts and the locked decisions behind them — read it for
> context, not as a work list. `PROJECT_STATUS.md` carries what is next.

**Audience: a future working session.** Written to be executed without re-deriving
anything. Read this top-to-bottom before touching code.

Anchored to commit `e49418b` ("feat: text and boolean cards, honest empty values"),
working tree clean, **418 tests passing**.

---

## 0. Working agreements (these override the project guide where they conflict)

1. **Docs are NOT the source of truth. The running app is.** `docs/` is a *reference*
   that we keep updated to match reality. the project guide says the opposite; the user has
   corrected this twice. When a doc contradicts the code: **the code wins**; fix the
   doc. Only ask first if the change alters *intent*, not when it records what is.
2. **Incremental.** One phase = one commit. **STOP before every commit**, print a
   suggested commit message, and wait for the user to commit before proceeding.
   Never run `git commit` yourself.
3. **Model economy.** The main loop runs an expensive model. Delegate straightforward
   implementation to the `principal-engineer` subagent with `model: "sonnet"` and a
   tight, complete brief. Keep in the main loop: design decisions, debugging, review
   of subagent output, and anything needing schema/validator probing.
4. **Verify empirically.** Do not trust tests alone. Drive the real app headlessly
   (`QT_QPA_PLATFORM=offscreen`) and probe the real validator. Every bug found so far
   was found this way, not by reading code.
5. **Ask when stuck.** Never guess architectural intent or invent BPX behaviour.
6. **Never leave stray processes.** `QMenu.exec()` genuinely blocks and cannot be
   monkeypatched; it will hang a test run forever. See §7.

---

## 1. Where the project stands

Committed, in order:

| Commit | What |
|---|---|
| `7938b1d` | docs: spec for the declared-kind input system |
| `e9cce6b` | Phase 1 — schema-driven classification core |
| `a134ee4` | Phase 2 — remove parameter (context menu + Delete) |
| `d36066b` | fix — validity badge scoped to its own parameter while typing |
| `e49418b` | Phase 3 — TextCard, BooleanCard, honest empty values, commit-when-edited |

### Current `ParameterKind` → card mapping (`app/ui_qt/cards/registry.py`)

| Kind | Card today | Status |
|---|---|---|
| `SCALAR` | `ScalarCard` | final |
| `INTEGER` | `IntegerCard` | final |
| `TEXT` | `TextCard` | final (Phase 3) |
| `BOOLEAN` | `BooleanCard` | final (Phase 3) |
| `ENUM` | `EnumCard` | final |
| `UNKNOWN` | `RawCard` | final |
| `FUNCTION` | `ReadOnlyCard` if value is `dict`, else `FunctionCard` | **interim shim** |
| `MAP` | `ScalarCard` if numeric / `RawCard` if `None` / `ReadOnlyCard` if `dict` | **interim shim** |
| `SERIES` | `ReadOnlyCard` | **interim shim** |
| `TABLE` | `ReadOnlyCard` (default fallback) | **interim shim** |

Phases 4b/4c remove every shim.

### Key invariants already established (do not break)

- **Kind is declared; mode is chosen.** `classify()` is metadata-authoritative and
  never uses value shape when `meta` exists. Value shape classifies *only* when
  `meta is None`.
- **A declared leaf field is always a `ParameterItem`, never a `TreeNode`.**
  `_is_object_node(value, meta)` consults `meta.is_container`.
- **`is_dirty` = `self._touched and not _values_equal(value(), original)`.**
  An untouched card is *never* dirty, whatever `value()` returns. This protects a
  stored `null` (a `TextCard` renders and reads back `""` for it).
  `_values_equal` is type-aware: `5 != 5.0`, `True != 1`.
- **Cards emit raw input and never judge schema validity.** The validator decides.
- **Badge + Issues-tab count are parameter-scoped**, on selection and while typing
  (`DocumentSession.preview_parameter_issues`).

---

## 2. Verified facts (with the commands that prove them)

Re-run any of these if something seems off. All were confirmed at `e49418b`.

### 2.1 Value edits are NOT undoable — the headline defect

`DocumentSession.apply_value()` mutates + rebuilds but **never pushes `_undo_stack`**.
Only `execute_command()` does.

```bash
cd app && python -c "
import sys, tempfile; sys.path.insert(0,'.')
from pathlib import Path
from state.app_state import AppState
d = Path(tempfile.mkdtemp())/'t.json'; d.write_bytes(Path('../examples/spm_example_valid.json').read_bytes())
st = AppState(); st.open(d); s = st.active
cap = lambda: s.document.raw['Parameterisation']['Cell']['Nominal cell capacity [A.h]']
print('before:', cap()); s.apply_value(('Parameterisation','Cell','Nominal cell capacity [A.h]'), 999.0)
print('after :', cap()); s.undo(); print('undo  :', cap(), '<- unchanged: NOT undoable')"
```

`docs/03-features.md:270` claims *"Command-based mutation with undo | Implemented"* —
false for value edits. Fixed in **Phase 4a**.

### 2.2 The fix is a reroute; everything needed already exists

- `core/commands.py` already defines `SetValue`, `AddSection`, `RemoveSection`,
  `AddParameter`, `RemoveParameter`, `CreateDocument`.
- `command_service.execute(SetValue)` returns
  `CommandResult(new, "Set value", command.path[:-1], command.path)` —
  i.e. **it already re-selects the edited parameter**, so rerouting `apply_value`
  through it preserves today's selection behaviour. No regression.
- `DocumentSession.can_undo` already exists.

### 2.3 `ParameterKind.TABLE` is unreachable for declared BPX fields

Kind census over `examples/` — **`table` never occurs**:

| File | kinds |
|---|---|
| `nmc_pouch_cell_BPX.json` | enum 1, function 8, integer 1, scalar 43, **series 8**, text 3 |
| `spm_example_valid.json` | enum 1, function 6, integer 1, **map 2**, scalar 32, text 2 |
| `lfp_18650_cell_BPX.json` | enum 1, function 8, integer 1, scalar 43, text 3 |

Because `OCP [V]` is declared `FloatFunctionTable`, a stored `{x,y}` classifies as
**FUNCTION**, not TABLE. `TABLE` only arises under `User-defined` (no metadata).

**Consequence:** the interpolated-table grid is *not* a standalone card for real BPX
data — it is the `InterpolatedTable` **mode body inside the FUNCTION card**. The grid
is therefore a *dependency* of the mode strip, which is why the phases were resequenced.

`SERIES` (the 8 experiment arrays) has exactly one representation, needs no strip, and
is read-only today → it is the cheapest real win.

### 2.4 `material_check` is strict

On `Initial hysteresis state: Negative electrode` in `spm_example_valid.json`, whose
Negative electrode is **single-particle** (Positive is blended: `Primary`, `Secondary`):

```
1.0                → valid
{"Primary": 1.0}   → INVALID   (electrode is single-particle)
{}                 → INVALID
{"Bogus": 1.0}     → INVALID   (key is not a particle name)
```

So `dict[str, FloatInt]` is legal **only** on a blended electrode, keys matching its
`Particle` names exactly. `ParameterItem.key_suggestions` (Phase 1) already carries
those names and is empty precisely when the dict mode can never be valid.

### 2.5 Empty / null semantics (settled, implemented)

```
Header.Title = null   → INVALID ("Input should be a valid string")
Header.Title = ""     → VALID
Header.Title absent   → VALID (optional)
Header.BPX   = ""     → INVALID (pattern ^\d+\.\d+(?:\.\d+)?$)
numeric = null or ""  → INVALID (both) — we write null, the honest "no value"
```

### 2.6 `nullable` is unreachable; `pattern` has exactly one field

The only nullable field in the whole schema is `UserDefined.description`, and
`field_meta()` returns `None` for `User-defined` paths. **Never build a "Set to null"
affordance** — it would be dead UI. `Header.BPX` is the only field with a `pattern`.

---

## 3. Locked decisions for Phases 4–6

Approved by the user. Do not relitigate; implement.

| # | Decision |
|---|---|
| **A** | Route `apply_value` through `execute_command(SetValue(...))` so value edits are undoable. **Add a toolbar Undo action + keyboard shortcut** — "neat, tidy, professional". |
| **B** | **Resequence**: undo fix → grid + SERIES → mode strip (FUNCTION + MAP) → takeover/paste/CSV → tree editing. The grid must exist before the strip (see §2.3). |
| **C** | Mode-switch semantics: switching mode **alone is never dirty** and never triggers preview validation; **no seeding** between modes (switching *completely changes* the value, so `3.7 → InterpolatedTable` gives an *empty* grid); each mode keeps its own draft until commit or Escape; **Escape reverts value *and* mode**. |
| **D** | Raw is **not** a permanent tab. A kind with one structured representation (SERIES, TABLE) shows **no strip**; if its value is unrepresentable the registry hands it a Raw editor with a notice. A union kind (FUNCTION, MAP) shows a strip, and `Raw` is appended **only when the committed value is unrepresentable**, decided **once at card construction** so the strip never mutates under the cursor. All modes stay clickable — clicking `FloatInt` on unrepresentable JSON just gives an empty numeric editor (nothing is destroyed until commit). |
| **E** | Mode labels are **verbatim `bpx.schema` vocabulary**, never translated. FUNCTION → `FloatInt` · `Function` · `InterpolatedTable`. MAP → `FloatInt` · `dict[str, FloatInt]`. (`FloatFunctionTable = Union[float, int, Function, InterpolatedTable]`; `float`+`int` fold into the one `FloatInt` button — bpx's own alias for exactly that union, and what the numeric editor already emits.) `Raw` is the sole non-schema label, because it is an app concept, not a BPX type. |
| **F** | The MAP `dict[str, FloatInt]` mode is **offered even on a single-particle electrode**, where it is guaranteed invalid. Guidance informs; it does not lock. Locking would make the UI a second, weaker validator. The row editor simply has no key suggestions there. |

### The vocabulary rule, concretely

Type words come straight from `bpx.schema` with **no translation**, even when they
look technical — modellers want `FloatFunctionTable`, not "Number or Function".
Already applied in `add_parameter_popup._kind_label`:

| Flag | Label |
|---|---|
| `is_enum` | `enum` |
| `is_integer` | `int` |
| `is_text` | `str` |
| `is_series` | `list[FloatInt]` |
| `allows_map` | `FloatInt \| dict[str, FloatInt]` |
| `allows_function` | `FloatFunctionTable` |
| default | `FloatInt` |

The `Function` mode's hint text should quote `bpx.Function`'s docstring
("operators: `* / - + **`, math functions `exp`, `tanh`, single variable `x`") so it
tracks the package.

---

## 4. Phase briefs

Each phase = one commit. Stop before each.

### Phase 4a — Undo correctness + Undo UI

**Goal.** Value edits become undoable, and Undo becomes reachable by users.

**Core change.** In `app/state/document_session.py`:
```python
def apply_value(self, path, value) -> None:
    if self.document is None:
        raise ValueError("No document loaded")      # keep this guard
    self.execute_command(SetValue(tuple(path), value))
```
`execute_command` already pushes `_undo_stack`, sets `dirty`, and (per §2.2) restores
`selected_path` / `selected_parameter_path` to the edited parameter — same visible
behaviour as today, plus undo.

**UI change.** `app/ui_qt/main_window.py`:
- Add an `Undo` action to the toolbar (text action, matching `Save` / `Export`; place
  it after `Export`, before `Search`). Greyed when `not session.can_undo` or no
  document — the established "built-but-inapplicable actions are greyed" convention.
- Shortcut: `QKeySequence.Undo` (`Ctrl+Z`).
- **Focus-aware dispatch** (important): a toolbar `QAction`'s shortcut is matched
  *before* the focused widget sees the key, so a naive binding steals `Ctrl+Z` from
  every text field. `_undo()` must therefore check `QApplication.focusWidget()` first:
  if it is a `QLineEdit` / `QPlainTextEdit` / `QTextEdit` whose own undo is available
  (`isUndoAvailable()`, or `document().isUndoAvailable()`), call the widget's `undo()`.
  Otherwise perform document undo. This works out cleanly: after a commit the card is
  rebuilt with a fresh widget (no text history), so `Ctrl+Z` reaches document undo.
- After a document undo: `self._refresh_all()`, then re-navigate to
  `session.selected_path` if set. Refresh the Undo action's enabled state whenever the
  document changes (there is an existing `_refresh_all` seam — reuse it, do not invent
  a new signal).

**Tests.** `apply_value` then `undo` restores the prior value; the undo stack grows one
entry per commit; Undo action disabled with no document and after the stack empties;
`Ctrl+Z` in a focused card input undoes typing, not the document; `Ctrl+Z` elsewhere
undoes the document; selection survives an undo.

**Do NOT** build Redo. There is none anywhere and it is a cross-cutting
`DocumentSession` change (see §6).

**Docs owed after this lands** (docs follow code): `03-features.md` §4 — the
"Command-based mutation with undo" row becomes honest; add an "Undo (toolbar +
`Ctrl+Z`)" capability row. `02-ui.md` toolbar section — add Undo to the action list.

---

### Phase 4b — Grid foundation + `SeriesCard`

**Goal.** Experiment arrays (`Time [s]`, `Current [A]`, `Voltage [V]`,
`Temperature [K]`) become editable. Build the grid the mode strip will reuse.

**Invariant (4b + 4c).** Grid and mode-body editors stay **detached** from
`document.raw`: copy values in via `set_values()`/`set_value()`, emit out via
`values()`/`value()`, commit only through `apply_value`. Never hold or mutate a live
list/dict from the document — undo correctness already requires this, and it keeps
every mutation attachable at the single choke point (future per-value provenance /
staged-proposal apply depend on that).

**New: `app/ui_qt/cards/grid.py` — `NumericGrid(QWidget)`**
- `QTableView` + a small `QAbstractTableModel`. **Not `QTableWidget`** — validation
  series run to thousands of rows.
- Constructed with column headers: `("Time [s]",)` for SERIES, `("x", "y")` for
  InterpolatedTable.
- **Cells hold `object`, not `float`.** A cell the user types `oops` into keeps the
  string `"oops"`. `value()` returns those objects verbatim. This preserves "cards
  emit raw input and never gatekeep" — the validator reports the type error. **Never
  coerce a bad cell to `0`.**
- Reuse the existing lenient parse convention (text → `int`/`float` when it parses,
  else the raw string). Extract that duplicated logic from `scalar.py` / `function.py`
  / `raw.py` into a shared `app/ui_qt/cards/values.py`
  (`format_value(v) -> str`, `parse_value(text) -> object`, empty → `None`) and have
  those three cards use it. Pure refactor, no behaviour change — assert that with the
  existing tests.
- API: `values()`, `set_values()`, `insert_row()`, `remove_row()`, `changed` signal,
  `row_count`.
- Compact inline height: ~8 visible rows, then scroll. Row-number gutter.
- Toolbar beneath: `+` / `−` row. (Paste and CSV are **Phase 5**; do not stub buttons
  for them — no disabled placeholders.)

**New: `app/ui_qt/cards/series.py` — `SeriesCard(EditorCard)`**
- One-column grid, header = the parameter's alias (which carries the unit).
- `value()` → the list of cell objects. An empty grid → `[]`.
- `None` (freshly added parameter) → empty grid. Untouched ⇒ not dirty ⇒ Enter commits
  nothing. (The `_touched` flag already gives this for free.)
- `reset()` restores the original rows.

**Representability predicate** (registry-level, mirrors the existing FUNCTION shim):
a SERIES value renders in the grid iff it is `None`, or a `list` whose every item is
`int | float | str` **and not `bool`**. Otherwise → `ReadOnlyCard` (today's behaviour,
so no regression). The real Raw editor arrives in 4c; **do not build it here.**

**Registry.** `SERIES` → `SeriesCard` (or `ReadOnlyCard` per the predicate).
`TABLE` → keep the `ReadOnlyCard` default for now; it becomes `TableCard` in 4c.

**Tests.** Editing a cell changes `value()`; a non-numeric cell survives as a string;
`+`/`−` rows; empty grid → `[]`; `None` → empty grid and not dirty; a non-list value
falls back to `ReadOnlyCard`; the `values.py` refactor leaves scalar/function/raw
behaviour byte-identical.

---

### Phase 4c — Mode strip: `FunctionCard` + `MapCard`

**Goal.** Union-typed fields expose every legal representation and can convert between
them. Removes the last shims.

**New: `app/ui_qt/cards/modal.py`**

- `ModeBody(QWidget)` — a tiny protocol, **not** an `EditorCard`:
  `value()`, `set_value(v)`, `reset()`, `focus_widget()`, signal `changed`.
  Bodies needed: `NumberBody` (line edit + unit), `ExpressionBody` (line edit +
  `bpx.Function` docstring hint), `TableBody` (2-column `NumericGrid`),
  `MaterialMapBody` (key/value grid), `RawJsonBody` (see below).
- `ModalCard(EditorCard)` — owns a mode strip (segmented buttons) over a
  `QStackedWidget` of bodies.
  - Bodies are built eagerly and **kept alive**, so each mode retains its own draft.
  - Only the **initial** mode's body is seeded from the committed value; every other
    body starts **empty** (decision C — "completely change it").
  - Switching mode: swap the stacked page. Do **not** emit `draft_changed`, do **not**
    set `_touched`, do **not** kick the preview debounce. (This also stops the badge
    flashing "Invalid" on an empty new mode.)
  - `value()` → active body's `value()`.
  - `is_dirty` → inherited unchanged: `_touched and not _values_equal(...)`. `_touched`
    is set only by a body's `changed` signal. Verify: `3.7` → switch to `Function` →
    press Enter ⇒ **no commit**. Type `2*x` → Enter ⇒ commits `"2*x"`.
  - `reset()` (Escape): reset **every** body, switch back to the initial mode. The base
    `_reset_draft` clears `_touched` *after* `reset()` — keep that ordering.
  - Install the keyboard handler on each body's `focus_widget()`.

**`RawJsonBody`** — a `QPlainTextEdit` of JSON, with a notice label explaining why the
value could not be shown structurally.
- **This is the one card that gates on *syntax*.** If the text is not parseable JSON,
  refuse to commit and show an inline parse error. Committing unparseable text as a
  *string* would replace `{"x":[...],"y":[...]}` with a broken string — that is data
  loss, not "an invalid edit". The distinction to hold: the card never judges **schema
  validity** (the validator owns that); it may refuse a draft that has **no
  representation at all**.
- Mechanism: add `commit_blocked_reason() -> str | None` to `EditorCard`, returning
  `None` by default. `InspectorPanel._on_commit` checks it before committing and
  surfaces the reason. `RawJsonBody`'s card overrides it.

**`FunctionCard(ModalCard)`** — modes `FloatInt` · `Function` · `InterpolatedTable`
(+ `Raw` when unrepresentable).
Initial mode from the committed value:
```
int/float (not bool) → FloatInt
str                  → Function
dict                 → InterpolatedTable  iff keys == {x, y}, both lists,
                                          len(x) == len(y), items int|float|str
None                 → FloatInt           (first declared member)
anything else        → Raw                (list, bool, ragged/extra-key dict, …)
```
A **ragged** `{"x":[1,2],"y":[1]}` is *not* representable — a grid is rectangular, and
padding it would invent data. It opens in `Raw` with a notice.

**`MapCard(ModalCard)`** — modes `FloatInt` · `dict[str, FloatInt]` (+ `Raw`).
- Initial: numeric → `FloatInt`; `dict` of `str → int|float|str` → dict mode; else `Raw`.
- `MaterialMapBody`: key/value rows. Existing keys shown. A `+ material ▾` button lists
  `parameter.key_suggestions` (the sibling `Particle` names from Phase 1). Keys are
  editable text — an unknown key is allowed and committed; **the validator judges it**
  (memory: *validator is source of truth*). Do not paint a key red or block it.
- Per decision F, the dict mode is offered even when `key_suggestions` is empty.

**`TableCard`** — `TABLE` kind (User-defined only). A bare `NumericGrid` with `x`/`y`,
no strip; unrepresentable → Raw.

**Registry after 4c** — no shims remain:
`SCALAR→ScalarCard`, `INTEGER→IntegerCard`, `TEXT→TextCard`, `BOOLEAN→BooleanCard`,
`ENUM→EnumCard`, `FUNCTION→FunctionCard`, `MAP→MapCard`, `SERIES→SeriesCard`,
`TABLE→TableCard`, `UNKNOWN→RawCard`.

**Tests.** Initial-mode selection for each shape above; mode switch alone is not dirty
and commits nothing; per-mode drafts survive a round trip (`FloatInt` → `Function` →
`FloatInt` still shows `3.7`); Escape restores value *and* mode; ragged table opens in
Raw; unparseable JSON blocks commit with a reason; a `FloatInt` → `InterpolatedTable`
conversion commits a real `{x,y}` dict; `MapCard` seeds `+ material` from
`key_suggestions` and commits an unknown key without complaint.

**Sanity check to run afterwards.** `preview_parameter_issues` must cope with a `dict`
or `list` draft. It should already — Phase 1's metadata-driven `_is_object_node` keeps
a declared leaf a `ParameterItem` whatever it holds — but drive it once to be sure.

---

### Phase 5 — Takeover editor, paste, CSV import, sibling columns

- **Expanded editor**: replaces the `ParameterCard` **inside the Inspector pane**
  (never a floating window) with a `✕` to return. Tree and parameter list stay visible.
  Convention: *in-place takeover = editing; floating dialog = read-only visualisation*
  (Analysis §9 keeps its floating launcher).
- **Paste**: auto-detect delimiter (tab / comma / semicolon / whitespace), skip a
  non-numeric header row, show a preview reporting *rows parsed / cells rejected*,
  offer `Replace all` vs `Append`. Rejected cells are reported, **never zero-filled**.
- **CSV import**: for a Validation run, a column-mapping step (file columns →
  `Time [s]` / `Current [A]` / `Voltage [V]` / `Temperature [K]`), offering to fill all
  four from one file. For a 2-column table, assume `x,y` with an override.
- **Sibling columns**: a `SeriesCard` inside `Validation/<run>` shows its sibling
  experiment columns read-only alongside, so a length mismatch is visible while
  editing. This needs sibling data on `ParameterItem` (mirror how `key_suggestions`
  was seeded in `tree_model._seed_key_suggestions` — a post-pass, not threaded
  through `_build_node`).

Likely two commits: (i) takeover + paste, (ii) CSV + sibling columns.

---

### Phase 6 — Tree editing

Schema-fixed hierarchy ⇒ **no OneNote-style promote/demote.** Only the schema's real
degrees of freedom, via the same right-click convention (context menus never create at
row level… but *do* create at container level — sections and dict-keyed collections
are the containers; keep creation of *parameters* in the `+ Add parameter` header).

| Right-clicked | Menu | Why legal |
|---|---|---|
| a section | `Add section ▸` (schema-expected children absent) · `Remove section` | sections are present/absent, never repositioned |
| `Particle` container | `Add material…` | `dict[str, Particle]` — user-named keys |
| a material / a Validation run | `Rename…` · `Remove` | dict-keyed, names user-owned |
| `Validation` | `Add experiment…` | `dict[str, Experiment]` |

- `AddSection` / `RemoveSection` **already exist** in `commands.py` +
  `command_service.py`. `structure.can_remove()` exists. Only **`RenameKey`** is new
  (command + `editing.rename_key`).
- Removal is allowed even on required sections — the validator reports the damage
  ("guidance informs; it does not lock").
- Rename appears **only** on dict-keyed nodes. Schema property names are never editable.
- Renaming a `Particle` invalidates any `dict[str, FloatInt]` MAP keyed by the old
  name. Decide then: rename-with-cascade, or let the validator report it (**default:
  let the validator report it**, consistent with F).
- `RenameKey` moves the **address** (alias-path tuple) of every descendant of the
  renamed node. Any future address-keyed sidecar metadata (e.g. per-value provenance)
  must cascade on rename — record that requirement when designing `RenameKey`, even
  though no sidecar exists yet.

**Known blocker (since resolved):** `bpx_gateway.expected_fields()` used to raise
`ValueError` for the electrode sections. It now takes the section's live value and
discriminates the union from it (a `Particle` key means blended; an empty electrode
resolves to single-particle), so `Add section ▸` and the add-parameter popup both
enumerate electrodes normally.

---

## 5. Documentation owed (write after each phase, code-first)

`docs/` is a *reference* updated to match the app. Do not gate code on it.

- `03-features.md` §4 — "Command-based mutation with undo" becomes true (4a); add Undo
  UI capability; flip `Text editing` / `Boolean editing` to **Implemented**; flip the
  remaining input-system rows as each phase lands.
- `03-features.md` §4 "Input system" — **delete or caveat the "Set to null" bullet**;
  no reachable field is nullable (§2.6). This is stale spec I wrote before probing.
- `02-ui.md` — toolbar gains `Undo`; note the expanded-editor takeover once 5 lands.
- `01-architecture.md` — record that `apply_value` routes through `SetValue`, so the
  editing spine really is command-based.
- `PROJECT_STATUS.md` — **gitignored** (`.gitignore:87`), untracked, local-only. Keep it
  current anyway; the project guide tells a fresh session to read it. It currently points here.

---

## 6. Known debt (record, do not fix opportunistically)

- **No redo, anywhere.** `_undo_stack` is linear and undo-only. Cross-cutting.
- **`undo()` sets `dirty = True` unconditionally** — undoing back to the saved state
  still shows Modified.
- **`_undo_stack` is unbounded** and stores whole `BPXDocument` snapshots. Memory grows
  per commit. Cap it if it bites.
- **Educational parameter-metadata dataset** is an empty seam; 5 of 8 popover categories
  render empty.
- **`SUPPORTED_BPX_EXTENSIONS` vs hardcoded dialog filters** can drift.

---

## 7. Pitfalls already paid for

- **`QMenu.exec()` truly blocks.** `monkeypatch.setattr(QMenu, "exec", ...)` does *not*
  intercept it; the run hangs forever with no dismissal offscreen, leaving orphaned
  `python.exe` processes. Idiom that works (see `tests/test_remove_parameter.py`):
  a zero-delay `QTimer.singleShot` that closes `QApplication.activePopupWidget()`.
- **A `QAction` shortcut only fires while its widget holds real Qt focus.** That is why
  Delete on the parameter list is a `keyPressEvent` override, not a `QAction` shortcut.
  It is also why the menu action carries **no** `QKeySequence` (a cosmetic one rendered
  as "Remove parameter  Del" and was removed).
- **Cards must populate their input widget *before* connecting its change signal**,
  or construction marks the card `_touched` and a bare Enter commits.
- **`_reset_draft` clears `_touched` *after* `reset()`**, because `reset()` repopulates
  the widget and re-fires `textChanged`.
- Run tests from the repo root: `python -m pytest tests/ -q`. Headless Qt:
  `QT_QPA_PLATFORM=offscreen`.
- Two `PyparsingDeprecationWarning`s from `bpx` are expected and unrelated.

---

## 8. Definition of done for the whole track

- No `ReadOnlyCard` reachable for any *declared* BPX field.
- Every one of the schema's nine leaf shapes has a real editor.
- Every value edit is undoable, and Undo is reachable from the toolbar and `Ctrl+Z`.
- No value is ever silently coerced, truncated, or discarded.
- `docs/` matches the app.
