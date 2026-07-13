# PLAN — Authoring/completion track

**Audience: a future working session (or the user), executing without this
conversation's context.** Read top-to-bottom before touching code; do not re-derive
or relitigate. Design discussed and locked with the user 2026-07-13; every deferred
factual question was then probed against the real validator and is settled below —
there are no "verify later" items left in this plan.

Mockup of the target UI (approved): (internal design archive)

Anchored at commit `d6f4d9d` ("feat: redo"), working tree clean, **808 tests passing**.

---

## 0. Working agreements (same as the input-system track)

1. **The running app is the source of truth**; `docs/` is a reference updated to match.
2. **One phase = one commit. STOP before every commit**, print a suggested message,
   wait for the user. Never run `git commit` unprompted.
3. **Delegate straightforward implementation** to `principal-engineer` (sonnet) with a
   tight brief; keep design decisions, debugging, schema/validator probing, and review
   of subagent output in the main loop.
4. **Verify empirically** — drive the real app offscreen (`QT_QPA_PLATFORM=offscreen`)
   and probe the real validator. Every real bug so far was found this way, not by
   reading code.
5. Tests from repo root: `python -m pytest tests/ -q`. Fixture documents live in
   `tests/fixtures/` (NOT `examples/` — that directory was removed 2026-07-13).

---

## 1. What this track is

The app can edit what exists; it cannot show what is *missing*. This track adds
completion: a pure query for expected-but-absent structure, surfaced in the parameter
list ("fields to add") and on the Validation page (an "Outstanding" section).

**Completion is provably distinct from validation** (probed against the real
validator, not docs):

- `Cell` has a `mode="before"` validator (deprecated moved-fields check); if it
  raises, pydantic never runs Cell's field validation — deleting a required field
  from `Cell` leaves validator output **byte-identical**.
- An absent section yields exactly one `missing` diagnostic; required leaves inside
  are never enumerated.
- No `Header.Model` → the sole diagnostic is `missing ('Model',)`; `Parameterisation`
  is never validated at all.

So completion **cannot** be a filter over diagnostics. It is a **pure, stateless
projection over `(raw, model)`** — same shape as `structure.addable_child_sections`.
It never judges legality; the validator remains the only source of valid/invalid.
`docs/03-features.md` §8's "stateful completion layer" is over-designed — amend the
doc when the phases land; do not build the layer.

---

## 2. Verified facts (probed 2026-07-13; re-run if anything seems off)

All probed at `d6f4d9d` by validating factory skeletons and mutations of them through
`bpx_gateway.validate` and printing each diagnostic's `error_type` and `loc`.

| # | Fact | Evidence |
|---|---|---|
| V1 | **`State` is required by NO model.** `required_sections` listing `("State",)` for concrete models over-claims. | SPM/SPMe/DFN skeleton minus `State` → zero State-related diagnostics; SPM issue count identical (23) with and without `State`. `structure.py` even contradicts itself: line 27 lists `State` under `_OPTIONAL_TOP_LEVEL`. |
| V2 | **SPMe requires `Separator`; the factory doesn't scaffold it.** `_SEPARATOR_MODELS = {"DFN"}` is wrong. | `create("SPMe")` validates with `missing ('Separator',)`. SPM and DFN skeletons demand no extra sections — the other constants are correct in both directions. |
| V3 | **Union `missing` locs carry NO branch tags.** | Partial + electrode holding only `Thickness [m]` → exactly 8 diagnostics like `missing ('Negative electrode', 'Minimum stoichiometry')` — clean paths, pydantic settled the SPM branch. |
| V4 | **Diagnostic locs are section-relative, not root-absolute.** | Absent `Cell` → `('Cell',)` not `('Parameterisation','Cell')`; absent model → `('Model',)`. The existing diagnostic-attachment pass already normalizes this — absorption must reuse it, never re-derive paths. |
| V5 | **A committed-`null` `FloatInt` field yields TWO diagnostics**, one per union branch, with branch-suffixed locs. | `null` capacity → `float_type ('Cell','Nominal cell capacity [A.h]','float')` **and** `int_type (…,'int')`. Null-absorption must therefore absorb *all diagnostics attached to the parameter*, not match one loc. |
| V6 | **Garbage `Header.Model` (`"banana"`) → one `literal_error` at `('Model',)`, nothing else validated.** | `literal_error ≠ missing` → it stays red in Issues (user-typed bad value), while completion additionally shows the declare-model task. Both statements are true; show both — the task's action is also the remedy for the error. |
| V7 | **Adding an empty section immediately enumerates its inner fields.** | SPMe + empty `Separator` → the `('Separator',)` diagnostic is replaced by three field-level `missing` inside it. Decision M's cascade is real validator behaviour, not hope. |
| V8 | **`expected_fields` resolves fine with `model=None`** (picks the full `ElectrodeSingle`/`ElectrodeBlended` variants — see its docstring). | Suppressing suggestions under an undeclared model (decision C) is a **product choice** (focus the user on declaring a model; don't suggest fields against a model they haven't picked), NOT a technical impossibility. Do not "fix" the suppression on the grounds that the query would work. |
| V9 | Under Partial, a *present* sparse electrode draws real `missing` errors from whichever union branch pydantic settles on (V3's 8), while `expected_fields` resolves a different branch (`ElectrodeSingle`, 12 fields incl. `Porosity`, `Transport efficiency`). Obeying app "required" flags under Partial → `extra_forbidden` rejections. | Basis of decision C's Partial rule. |

Reusable probe (adjust as needed):

```bash
cd app && python - <<'EOF'
import sys, copy; sys.path.insert(0, '.')
from core import bpx_gateway, document_factory
doc = document_factory.create("SPMe", title="probe")
for d in bpx_gateway.validate(doc).issues:
    print(d.error_type, d.loc)
EOF
```

---

## 3. Locked decisions (user-approved; implement, do not reopen)

| # | Decision |
|---|---|
| **A** | **Shape:** `core/completion.py` exposes a per-section pure function mirroring `addable_child_sections` — `completion_for(path, value, model) -> (missing_fields, missing_child_sections)` — plus a document-level aggregation for the Validation page. No global stateful task-list type. No Qt imports. |
| **B** | **Terminology (exact words, everywhere):** *Expected* = schema names the field for this section. *Required* = schema requires it AND the model is concrete (SPM/SPMe/DFN). *Missing* = expected field with no entry in raw. *Outstanding* = Required and (absent OR committed `null`). "Valid/invalid" never appear in completion UI — those words belong to the validator's surfaces only. |
| **C** | **Models.** No model, or a garbage/unknown `Header.Model` value: the only completion task is "declare a model", and the parameter-list "fields to add" group is suppressed (product choice — see V8; per V6 a garbage value *also* stays red in Issues, and both appear). An absent `Header` collapses to one "Header — section absent" row per M; the declare-model task appears once Header exists. `Partial` → suggest every expected field, flag **nothing** Required (V9). Concrete models → Required flags as-is (they match the validator). |
| **D** | **Null rule:** a **Required** field holding committed `null` is **Outstanding ("added, no value yet"), not an Issue**. `null` is the app's own honest-empty sentinel — it means unfinished, not wrong. A user-typed bad value stays an Issue. The parameter's own inline badge still reports the validator verbatim. **Deliberately required-only** (edge-case review offered generalising to optional/custom null fields; the user chose no): an optional or custom parameter added-but-unfilled shows as a red Issue, as today. Do not "fix" this asymmetry — it is chosen. Only literal `null` qualifies — an empty list on a series is a committed (invalid) value and stays red. |
| **E** | **Absorption:** a validator diagnostic with `error_type == "missing"` whose location corresponds to an Outstanding item is shown **only** in Outstanding; plus, per D and V5, **every diagnostic attached to a committed-null Required parameter** is absorbed (a null union field raises two). Matching happens at the attachment level — reuse the exact normalization the diagnostic-attachment pass computes (V4); never invent a second path-matching scheme. Safety net: a `missing` diagnostic NOT covered stays in Issues — the real remaining cases are Partial's union-branch demands (V9) and any path `expected_fields` cannot resolve. (Since the electrode-union fix, `expected_fields` DOES resolve `Validation/<run>` and `Particle/<material>`, so missing fields inside an *existing* user-named entry absorb normally.) The validator is never silenced, only re-seated. |
| **F** | **Placement:** one Validation page, two sections — **Issues** (unchanged) above **Outstanding** (fed by `core.completion` only). No new rail entry. Missing whole sections appear **only** here, never as ghost tree nodes — the tree stays an honest view of what exists. |
| **G** | **Rail badge = post-absorption Issues count**, derived from the same function that fills the Issues section so the two can never disagree. A fresh skeleton shows no red badge (Issues 0, Outstanding N). User explicitly accepted this change to the badge's meaning: red = "something is wrong", never "something is unstarted". |
| **H** | **Parameter list:** one collapsed line at the end of the real rows — "▸ N fields to add" — closed by default; expands to compact name+`+` rows (absent expected fields only; committed-null fields are already real rows). `+` = `AddParameter(None)` then reveal/focus the new editor — the add-parameter popup's Suggested path verbatim, one undo step. Required tag reuses `style.REQUIRED`; under Partial no Required tags, suggestions still listed. **The group's expanded state survives rebuilds of the same section** (every `+` commits a command → rebuild; a stateless group would snap shut after each add) and resets on navigation to a different section. |
| **I** | **An empty electrode shows single-particle suggestions immediately** (matches the existing popup + discriminator "empty ⇒ single" behaviour; guidance informs, never locks). |
| **J** | **Set-model action is in scope** (new, minimal): a chooser that commits `Header.Model` through the existing command spine — `apply_value` already routes `("Header","Model")` strings to `ChangeModel`, which also adds required-but-missing sections in the same undo step. Reuse it; build no new command. This makes the "declare a model" row actionable (no disabled placeholders). |
| **K** | **Recompute on commit only.** Completion is a function of the committed raw dict; drafts never touch it. Do not wire into preview. |
| **L** | **Activation contract** (Enter/double-click; selection alone never acts — the existing Issues keyboard contract, kept everywhere): Issue → navigate (unchanged). ○ missing field → navigate to the owning section, expand the fields-to-add group, highlight the row (no mutation; the `+` mutates). ◐ added-no-value → navigate to the parameter's editor. Section absent → `AddSection` then navigate into it (one undo step; there is nothing to navigate to first). Declare model → open the set-model chooser. Every Outstanding row displays its action text — nothing mutates without saying so. |
| **M** | **Absent section = one row.** Its fields enumerate only once it exists — mirrors the validator's own collapsing, and needs no cascade code because per-section recompute gives it free (V7 proves the validator does the same). |
| **N** | **Deferred, recorded, not built:** "add at least one material/experiment" tasks for user-named collections (blended `Particle`, `Validation` runs — existing entries DO enumerate their fields; only the "collection is empty" prompt is deferred); save-as-template / new-from-template; compound rail badge; the live-preview Issues-count debt (unrelated, stays as recorded in PROJECT_STATUS). |

### UI copy (pinned so all phases use identical words; matches the mockup)

| Where | Copy |
|---|---|
| Page section headers | `Issues` · `Outstanding` |
| Outstanding group header | `<Section> — N of M remaining` / `<Section> — section absent` |
| Missing-field row | alias, `REQUIRED` tag where applicable, action `Go to ›` |
| Null-field row | `<alias> — added, no value yet`, action `Go to ›` |
| Absent-section row | section name, action `+ Add section` |
| Declare-model row | `Declare a model`, action `Choose…` |
| Empty states | `✓ No issues` · `✓ Nothing outstanding` · Partial: `Model is Partial — no completion target. Expected fields are still suggested in each section's parameter list.` |
| Parameter-list group | `▸ N fields to add` (collapsed) / `▾ N fields to add` (expanded), compact rows with `+` |

---

## 4. Phases (dependency order; one commit each; STOP before each commit)

### Phase 1 — `structure.py` tells the validator's truth
Two verified bugs, one bounded refactor, no UI:
- `_SEPARATOR_MODELS` → `{"SPMe", "DFN"}` (V2).
- `required_sections` drops `("State",)` (V1) — it must mean what its name says.
- **Factory/ChangeModel behaviour is preserved deliberately**: `document_factory.create`
  and `command_service`'s ChangeModel iterate `required_sections` today, and `State`
  should stay in fresh/converted documents as UX scaffolding. Introduce an explicit
  scaffold list (`required_sections(model)` + `("State",)` for concrete models) used by
  those two callers, so the scaffolding choice is named instead of smuggled.
- Tests: `create("SPMe")` contains `Separator` and draws no section-level `missing`;
  `create(model)` still contains `State` for concrete models; `required_sections`
  excludes `State` and includes `Separator` for SPMe/DFN; ChangeModel to SPMe adds
  `Separator`. Check existing fixtures/tests asserting the old SPMe shape.

### Phase 2 — `core/completion.py`
The pure query (decisions A–E, I, K, M). No Qt; unit tests only. The test that earns
the layer's existence: nmc-with-deleted-Cell-field (fixture
`tests/fixtures/nmc_pouch_cell_BPX.json`), where completion reports the task the
validator cannot see. Also: the Partial case (zero Required, full Expected);
null-counts-as-outstanding (and `[]` does not); undeclared/garbage model → single
declare-model task; absent section → one item, fields enumerated once present.

### Phase 3 — Parameter-list "fields to add" group
Decision H. Derived in the UI from `core.completion`; **never** injected into
`TreeNode.parameters` — the tree and parameter model keep meaning "what is in the
document". Drive the real app: add several fields in a row and verify the group stays
expanded and focus lands in each new editor.

### Phase 4 — Set-model action
Decision J. Needed before Phase 5 so the declare-model row has an action. Placement:
with the document-identity UI (top bar shows Title · Model · BPX version). Verify
ChangeModel's section-scaffolding behaviour through the real app.

### Phase 5 — Validation page: Outstanding section + absorption + badge
Decisions E, F, G, L, and the pinned copy. Absorption matching reuses the
diagnostic-attachment normalization (V4); union locs are clean (V3) so no
branch-stripping is needed for `missing`; null absorption is attachment-level (V5).
The badge and the Issues section derive from one function. Drive the real app through
mockup states 1–4 (skeleton / working doc / Partial / complete) and compare against
the mockup.

Docs owed as phases land (code-first): `03-features.md` §5/§8 (completion architecture
→ stateless projection; Validation page two-section layout; absorption rule);
`02-ui.md` (parameter-list group, page layout, badge meaning); `04-roadmap.md` (list
this track — it currently omits it entirely). `PROJECT_STATUS.md` after every phase.

---

## 5. Pitfalls carried forward

- `QMenu.exec()` truly blocks offscreen; dismiss popups via zero-delay
  `QTimer.singleShot` closing `QApplication.activePopupWidget()`.
- Cards/widgets populate **before** connecting change signals, or construction marks
  them touched.
- A `QAction` shortcut fires only with real Qt focus; two `QShortcut`s on one window
  with the same sequence go ambiguous and NEITHER fires.
- Two `PyparsingDeprecationWarning`s from `bpx` are expected and unrelated.
- `PROJECT_STATUS.md` is gitignored — keep it current, never commit it.

## 6. Definition of done for the track

- A user can author a complete document by filling in what the app shows, never by
  hunting: every Required absence is visible either as a "fields to add" entry or an
  Outstanding row, in every model state, including the states where the validator
  itself goes blind (V1's Cell suppression, absent sections, undeclared model).
- Red means wrong, never unstarted; nothing the app itself wrote (a scaffolded
  section, a `null` from `+`) ever presents as an error on a Required field.
- The validator is never silenced — every diagnostic is visible on the page, in
  exactly one of the two sections.
- All five phases landed as separate commits; docs match the app; the full suite is
  green with the new unit and driver tests.
