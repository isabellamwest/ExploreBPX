# PLAN — Authoring/completion track

> **⚠ This is a plan, not a spec — a proposal that can change, not a locked
> requirement.** Where it and the running app differ, the app is correct. Read it
> as context for the decisions taken, not a mandate to implement verbatim; re-check
> against the code and confirm with Bella before acting on anything still open.

**Audience: a future working session (or the user), executing without this
conversation's context.** Read top-to-bottom before touching code; do not re-derive
or relitigate. Design discussed and locked with the user 2026-07-13; every deferred
factual question was then probed against the real validator and is settled below —
there are no "verify later" items left in this plan.

Mockup of the target UI (approved): (internal design archive)

Anchored at commit `d6f4d9d` ("feat: redo"), working tree clean, **808 tests passing**.

> **AMENDMENT 2026-07-20 (bpx 1.1.0 → 1.1.1, user-approved bump).** The validator's
> truth changed and the app followed it: `State` is now **schema-optional for every
> model** (`state: State = Field(None)`), the root *"'State' section must be
> provided"* validator was **deleted upstream**, and `State`'s children are nullable.
> V1 below and Phase 1's "`required_sections` keeps `("State",)`" instruction are
> **superseded** — `required_sections` no longer lists `State`, and `completion.py`'s
> State-absorption special case was removed. Additionally, 1.1.1 auto-converts legacy
> v0.x files (a new `is_legacy_bpx` pre-check reads `Header.BPX` *before* pydantic —
> a missing `Header.BPX` now surfaces as a raw exception diagnostic, not a pydantic
> `missing`). The superseded text below is kept as the verified 1.1.0 record.

> **AMENDMENT 2026-07-20 (diffusivity/null-field absorption, fix landed 03849b6).**
> V5 undercounts: a committed-null **function/table union** field draws **four**
> diagnostics (`float_type`/`int_type`/`string_type`/`model_type`), and pydantic
> tags the function/table branches with names (`function-after[validate(), str]`,
> `InterpolatedTable`) no exact-match denylist can keep up with. The fix therefore
> abandons tag-stripping for resolvable parameters: when `_attach_issues` resolves
> a `ParameterItem`, the stored nav_path IS that parameter's canonical `.path`.
> `_NAV_STRIP_TAGS` is **deliberately untouched** (fallback for unresolvable locs
> only — do not widen it). nav_path serves two masters that strip differently:
> **identity** (absorption keying) uses the full canonical path; **display**
> (section headings) strips a leading `Parameterisation` only, never `Header` —
> owned by `core.page_buckets.strip_parameterisation_prefix`; do not merge it with
> `completion._nav_path_candidates`, which strips both for loc-matching. Pinned by
> `test_partition_null_function_table_field_absorbs_all_four_branches` and the
> null-every-field walk in `test_completion.py`.

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
- The suppression is layered THREE deep (fully mapped 2026-07-14): bpx's root
  dispatcher validates `Header` FIRST and uncaught — an invalid `Header` field
  suppresses ALL of `Parameterisation`/`State`/`Validation` (a bad `Cell` field
  alongside a bad `Header` field shows only the Header diagnostic). Then the root
  `mode="before"` validator short-circuits on ANY `Parameterisation` problem, hiding
  ALL `State`/`Validation` diagnostics — including the root-level demand for `State`
  itself (corrected V1). Then per-section `mode="before"` validators (e.g. `Cell`)
  hide their own fields. This is *why* completion cannot be read off diagnostics at
  any layer. A skeleton
  document therefore reveals nothing about the State subtree.
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
| V1 | **SUPERSEDED 2026-07-20 — bpx 1.1.1 made `State` optional; see the amendment at the top. 1.1.0 record follows.** **CORRECTED 2026-07-14 (user: "follow validator precisely"): `State` IS validator-required for concrete models**, via bpx's root `mode="before"` validator — *"'State' section must be provided unless using a 'Partial' parameterisation"* — emitted as a root-level `value_error` at `loc=()`, NOT a `missing`. The original V1 ("required by no model") was an artifact: the root validator short-circuits on ANY `Parameterisation` problem, and every skeleton has one, so skeleton probes never saw it. **The suppression is broader than first recorded**: any Parameterisation issue hides ALL State/Validation diagnostics, not just Cell's. `State`'s own children `Initial conditions` and `Thermal environment` are schema-required once State exists. | Valid SPM fixture minus `State` → `value_error ()` with the message above; minus `State.Thermal environment` → `missing ('State','Thermal environment')`; empty `State` → both children `missing`. Skeleton probes show none of these. So `required_sections` keeps `("State",)` for concrete models — it was right all along. |
| V2 | **SPMe requires `Separator`; the factory doesn't scaffold it.** `_SEPARATOR_MODELS = {"DFN"}` is wrong. | `create("SPMe")` validates with `missing ('Separator',)`. SPM and DFN skeletons demand no extra sections — the other constants are correct in both directions. |
| V3 | **Union `missing` locs carry NO branch tags.** | Partial + electrode holding only `Thickness [m]` → exactly 8 diagnostics like `missing ('Negative electrode', 'Minimum stoichiometry')` — clean paths, pydantic settled the SPM branch. |
| V4 | **Diagnostic locs are section-relative, not root-absolute — and the convention is asymmetric** (fully mapped 2026-07-14): the validator DROPS a leading `Header` (`missing ('BPX',)` for absent `Header.BPX`) and a leading `Parameterisation` (`('Cell',)`), but KEEPS `State` and `Validation` prefixes in full (`('State','Thermal environment')`, `('Validation','C/20','Time [s]')`). The attachment pass passes unresolvable Header-relative locs through as-is (a missing-`BPX` diagnostic surfaces with nav_path `('BPX',)`). Absorption matching must therefore test the candidate prefixes (`loc`, `('Header',)+loc`, `('Parameterisation',)+loc`) — a strip that knows only `Parameterisation` leaves missing required Header fields double-surfaced (red Issue + Outstanding row), which was a real reviewed defect. Also noted: `Temperature [K]` is optional in `Experiment` (only Time/Current/Voltage are schema-required). |
| V5 | **A committed-`null` `FloatInt` field yields TWO diagnostics**, one per union branch, with branch-suffixed locs. | `null` capacity → `float_type ('Cell','Nominal cell capacity [A.h]','float')` **and** `int_type (…,'int')`. Null-absorption must therefore absorb *all diagnostics attached to the parameter*, not match one loc. |
| V6 | **Garbage `Header.Model` (`"banana"`) → one `literal_error` at `('Model',)`, nothing else validated.** | `literal_error ≠ missing` → it stays red in Issues (user-typed bad value), while completion additionally shows the declare-model task. Both statements are true; show both — the task's action is also the remedy for the error. |
| V7 | **Adding an empty section immediately enumerates its inner fields.** | SPMe + empty `Separator` → the `('Separator',)` diagnostic is replaced by three field-level `missing` inside it. Decision M's cascade is real validator behaviour, not hope. |
| V8 | **`expected_fields` resolves fine with `model=None`** (picks the full `ElectrodeSingle`/`ElectrodeBlended` variants — see its docstring). | Suppressing suggestions under an undeclared model (decision C) is a **product choice** (focus the user on declaring a model; don't suggest fields against a model they haven't picked), NOT a technical impossibility. Do not "fix" the suppression on the grounds that the query would work. |
| V9 | Under Partial, a *present* sparse electrode draws real `missing` errors from whichever union branch pydantic settles on (V3's 8), while `expected_fields` resolves a different branch (`ElectrodeSingle`, 12 fields incl. `Porosity`, `Transport efficiency`). Obeying app "required" flags under Partial → `extra_forbidden` rejections. | Basis of decision C's Partial rule. |

Reusable probe (adjust as needed). Note the `getattr`s: warning diagnostics
(`PythonWarningDiagnostic`) have neither `.error_type` nor `.loc`, and the nmc fixture
emits one — a bare `d.error_type` crashes on exactly the Phase-2 keystone document:

```bash
cd app && python - <<'EOF'
import sys, copy; sys.path.insert(0, '.')
from core import bpx_gateway, document_factory
doc = document_factory.create("SPMe", title="probe")
for d in bpx_gateway.validate(doc).issues:
    print(getattr(d, "error_type", None), getattr(d, "loc", None), d.message)
EOF
```

---

## 3. Locked decisions (user-approved; implement, do not reopen)

| # | Decision |
|---|---|
| **A** | **Shape:** `core/completion.py` exposes a per-section pure function mirroring `addable_child_sections` — `completion_for(path, value, model) -> (missing_fields, missing_child_sections)` — plus a document-level aggregation for the Validation page. No global stateful task-list type. No Qt imports. |
| **B** | **Terminology (exact words, everywhere):** *Expected* = schema names the field for this section. *Required* = schema requires it AND the model is concrete (SPM/SPMe/DFN). *Missing* = expected field with no entry in raw. *Outstanding* = Required and (absent OR committed `null`). "Valid/invalid" never appear in completion UI — those words belong to the validator's surfaces only. |
| **C** | **Models.** No model, or a garbage/unknown `Header.Model` value: the only completion task is "declare a model", and the parameter-list "fields to add" group is suppressed (product choice — see V8; per V6 a garbage value *also* stays red in Issues, and both appear). **Caveat, added 2026-07-14 with the Model chip's removal (Phase 4, revised):** the suppression exempts `Header`'s own group. Its rationale — don't suggest fields against a model nobody picked — never applied to `Header`, whose fields (`Title`/`Model`/`BPX`) are not model-dependent; Header was collateral of a gate aimed at the other sections. With no chip, Header's suggestion row for `Model` is *the* place a model gets declared, so suppressing it would leave the declare-model task with nowhere to land. An absent `Header` collapses to one "Header — section absent" row per M; the declare-model task appears once Header exists. `Partial` → suggest every expected field, flag **nothing** Required (V9). Concrete models → Required flags as-is (they match the validator). |
| **D** | **Null rule (REVISED 2026-07-14, second user ruling — supersedes the earlier required-only choice, which was reversed after seeing it live):** any **schema-expected** field holding committed `null` is **Outstanding ("added, no value yet")**, REQUIRED tag only where required. `null` is the app's own honest-empty sentinel — creating an expected field never makes the document look worse. **Custom parameters stay red**: their `extra_forbidden` rejects the *name*, not the emptiness — filling a value fixes nothing, so absorbing it would lie. A user-typed bad value stays an Issue everywhere. Only literal `null` qualifies — an empty list is a committed (invalid) value and stays red. |
| **E** | **Absorption:** a validator diagnostic with `error_type == "missing"` whose location corresponds to an Outstanding item is shown **only** in Outstanding; plus, per D and V5, **every diagnostic attached to a committed-null Required parameter** is absorbed (a null union field raises two). One deliberate exception to the missing-only rule (corrected V1): the **root `value_error` demanding `State`** (`loc=()`, message "'State' section must be provided unless using a 'Partial' parameterisation") absorbs into the State MISSING_SECTION task when that task exists — matched by its message, pinned by a regression test against the real validator so a bpx wording change fails loudly rather than silently un-absorbing. Matching happens at the attachment level — reuse the exact normalization the diagnostic-attachment pass computes (V4); never invent a second path-matching scheme. Safety net: a diagnostic NOT covered stays in Issues — the real remaining cases are Partial's union-branch demands (V9) and any path `expected_fields` cannot resolve. (Since the electrode-union fix, `expected_fields` DOES resolve `Validation/<run>` and `Particle/<material>`, so missing fields inside an *existing* user-named entry absorb normally.) The validator is never silenced, only re-seated. |
| **F** | **Placement:** one Validation page, two sections — **Issues** (unchanged) above **Outstanding** (fed by `core.completion` only). No new rail entry. Missing whole sections appear **only** here, never as ghost tree nodes — the tree stays an honest view of what exists. |
| **G** | **Rail badge = post-absorption Issues count**, derived from the same function that fills the Issues section so the two can never disagree. A fresh skeleton shows no red badge (Issues 0, Outstanding N). User explicitly accepted this change to the badge's meaning: red = "something is wrong", never "something is unstarted". |
| **H** | **Parameter list:** one collapsed line at the end of the real rows — "▸ N fields to add" — closed by default; expands to compact name+`+` rows (absent expected fields only; committed-null fields are already real rows). `+` = `AddParameter(None)` then reveal/focus the new editor — the add-parameter popup's Suggested path verbatim, one undo step. Required tag reuses `style.REQUIRED`; under Partial no Required tags, suggestions still listed. **The group's expanded state survives rebuilds of the same section** (every `+` commits a command → rebuild; a stateless group would snap shut after each add) and resets on navigation to a different section. |
| **I** | **An empty electrode shows single-particle suggestions immediately** (matches the existing popup + discriminator "empty ⇒ single" behaviour; guidance informs, never locks). |
| **J** | **Set-model action is in scope** (new, minimal): a chooser that commits `Header.Model` through the existing command spine — `apply_value` already routes `("Header","Model")` strings to `ChangeModel`, which also adds required-but-missing sections in the same undo step. Reuse it; build no new command. This makes the "declare a model" row actionable (no disabled placeholders). |
| **K** | **Recompute on commit only.** Completion is a function of the committed raw dict; drafts never touch it. Do not wire into preview. |
| **L** | **Activation contract** (Enter/double-click; selection alone never acts — the existing Issues keyboard contract, kept everywhere): Issue → navigate (unchanged). ○ missing field → navigate to the owning section, expand the fields-to-add group, highlight the row (no mutation; the `+` mutates). ◐ added-no-value → navigate to the parameter's editor. Section absent → `AddSection` then navigate into it (one undo step; there is nothing to navigate to first). Declare model → open the set-model chooser. Every Outstanding row displays its action text — nothing mutates without saying so. |
| **O** | **No validator output is ever dropped (user, 2026-07-14: "never remove any validation ever"):** every diagnostic renders somewhere on the page — an absorbed diagnostic shows on its Outstanding row as muted secondary text (its real validator message), uncovered ones stay in Issues (the fallback). Absorption re-seats; it never swallows. |
| **P** | **Empty-value row presentation:** a parameter whose committed value is `null` renders its parameter-list row in muted/grey (emptiness visible at a glance — covers both "never filled" and "value was removed", which raw cannot distinguish); the ⚠ marker means *page-visible* issues (the parameter list receives the partition's visible-issue paths from `_refresh_all`), so an expected-null field is grey without ⚠ while a custom-null field is grey **with** ⚠ (its `extra_forbidden` stays red on the page). The card *validity* badge and the Issues tab stay **validator-verbatim in message text and severity** — they are exempt from completion's calming/absorption (an inline surface always tells the truth about the selected parameter), but they DO apply Q's display de-dup (showing the validator's own words once, not twice). "Verbatim" = not calmed, not absorbed; it is not "un-deduplicated". |
| **Q** | **Union-pair display merge:** the `float_type` + `int_type` pair a single null/bad `FloatInt` value draws (V5) merges to ONE displayed message ("Input should be a valid number") in the Issues tab, the page Issues section, and Outstanding secondary text. Display-only — the validator, `parameter.issues`, and absorption bookkeeping are untouched; page counts/badge count merged display rows. |
| **R** | **Optional-null rows sit in a separate sub-group** (user, 2026-07-14): a section's required missing/null tasks stay under `<Section> — N of M remaining` (N and M both required-only, so the ratio always equals the counted rows beneath it — no "5 of 5" over 6 rows). Optional expected fields added-but-unfilled drop to a quiet sub-group header `<Section> · optional — K unfilled` beneath, clearly outside the completion target; they still carry their absorbed message (decision O). This keeps the completion ratio honest AND keeps optional validation visible. Ordering: within a section, required group then its optional sub-group, before the next section. |
| **M** | **Absent section = one row.** Its fields enumerate only once it exists — mirrors the validator's own collapsing, and needs no cascade code because per-section recompute gives it free (V7 proves the validator does the same). |
| **N** | **Deferred, recorded, not built:** "add at least one material/experiment" tasks for user-named collections (blended `Particle`, `Validation` runs — existing entries DO enumerate their fields; only the "collection is empty" prompt is deferred); save-as-template / new-from-template; compound rail badge; the live-preview Issues-count debt (unrelated, stays as recorded in PROJECT_STATUS). |

### UI copy (pinned so all phases use identical words; matches the mockup)

| Where | Copy |
|---|---|
| Page section headers | `Issues` · `Outstanding` |
| Outstanding group header | `<Section> — N of M remaining` / `<Section> — section absent` |
| Missing-field row | alias + `REQUIRED` tag, action `Go to ›`. Every Outstanding row is Required **by definition** (decision B) — `document_completion` returns required-only tasks; optional absences live solely in the per-section fields-to-add group (`completion_for`). The tag is kept anyway for vocabulary consistency with the add-parameter popup. |
| Null-field row | `<alias> — added, no value yet`, `REQUIRED` tag **only when the field is required** (decision D revised — optional expected nulls are Outstanding but untagged), the absorbed validator message as muted secondary text (decision O), action `Go to ›` |
| Absent-section row | section name, action `+ Add section` |
| Declare-model row | `Declare a model`, action `Choose…` |
| Empty states | `✓ No issues` · `✓ Nothing outstanding` · Partial: `Model is Partial — no completion target. Expected fields are still suggested in each section's parameter list.` |

| Parameter-list group | `▸ N fields to add` (collapsed) / `▾ N fields to add` (expanded; singular "field" when N=1), compact rows with `+` |

**Partial caveat (from V9, acknowledge, don't hide):** under Partial the fields-to-add
group stays populated (decision H) but is *informational, not a safe authoring path* —
an empty electrode suggests `ElectrodeSingle`'s 12 fields while pydantic settles the
document on the SPM branch, so following the suggestions can draw `extra_forbidden`
(red, in Issues, per E's safety net — correct and deliberate: the validator is never
silenced). The implementer must not "fix" this by suppressing either surface; the
Partial empty-state copy above is the user-facing acknowledgement.

---

## 4. Phases (dependency order; one commit each; STOP before each commit)

### Phase 1 — `structure.py` tells the validator's truth
One verified bug, no UI. (**Revised after V1's correction; State parts superseded
2026-07-20** — bpx 1.1.1 made `State` optional and `required_sections` no longer
lists it; see the amendment at the top. The 1.1.0-era brief follows as record.)
- `_SEPARATOR_MODELS` → `{"SPMe", "DFN"}` (V2). That is the whole code change.
- ~~`required_sections` keeps `("State",)` for concrete models~~ (superseded: it
  now tracks the 1.1.1 validator, which demands no `State`).
- Tests: `create("SPMe")` contains `Separator` and draws no section-level `missing`;
  `required_sections` includes `Separator` for SPMe/DFN; Partial/None
  return only Header+Parameterisation; ChangeModel to SPMe adds `Separator`.

### Phase 2 — `core/completion.py`
The pure query (decisions A–E, I, K, M). No Qt; unit tests only. The test that earns
the layer's existence: nmc-with-deleted-Cell-field (fixture
`tests/fixtures/nmc_pouch_cell_BPX.json`), where completion reports the task the
validator cannot see. **That test's premise is fixture-dependent**: the byte-identical
suppression holds because the nmc fixture already trips Cell's `mode="before"`
validator at baseline (`value_error ('Cell',)`). State this in the test's docstring so
a future fixture cleanup that makes nmc validate cleanly doesn't silently invert the
premise. (2026-07-20: exactly this happened — bpx 1.1.1 auto-converts the legacy nmc
fixture cleanly, so the test now injects the deprecated `Ambient temperature [K]`
into `valid_spm_dict` to trip the same `mode="before"` validator.) Also test: the Partial case (zero Required, full Expected);
null-counts-as-outstanding (and `[]` does not); undeclared/garbage model → single
declare-model task; absent section → one item, fields enumerated once present.

Alongside `completion_for`, this phase also delivers the second Qt-free function
Phase 5 needs:
`partition_issues(document, completion_result) -> (visible_issues, outstanding, badge_counts)`
— the absorption rule (E) as a pure function over the document's already-attached
diagnostics plus the completion output. Decision A's `completion_for` stays a
projection over `(raw, model)`; `partition_issues` is a separate pure function that
*consumes* diagnostics, so core stays Qt-free and the panel/badge share one derivation.

### Phase 3 — Parameter-list "fields to add" group
Decision H. Derived in the UI from `core.completion`; **never** injected into
`TreeNode.parameters` — the tree and parameter model keep meaning "what is in the
document". **New seam this phase must build** (nothing like it exists): a
parameter-list method to *reveal-and-highlight a missing alias* — expand the group and
select the synthetic row. Today `parameter_list.reveal` (parameter_list.py:130)
matches only real rows by role data, and `NavigationService.navigate`
(navigation.py:48) resolves only nodes/parameters that exist in the document —
neither can address a field that isn't there. Phase 5's "Go to ›" depends on this
method, so build and test it here (headless driver test: activate → group expanded,
synthetic row selected). Drive the real app: add several fields in a row and verify
the group stays expanded and focus lands in each new editor.

### Phase 4 — Set-model action
Decision J. **REVISED 2026-07-14 (user-decided): there is no set-model affordance of
its own.** The Model chip this phase originally shipped — a menu button in the top bar,
with an `open_model_chooser()` seam for Phase 5's declare-model row — has been removed.
It was redundant: `Header.Model` is an ordinary enum field, and the Editor's normal
commit path (`InspectorPanel` → `session.apply_value`) already routes
`("Header","Model")` to `ChangeModel`, which adds the target model's missing required
sections in the same undo step (removes nothing; fully undoable ⇒ no confirmation
dialog). The chip was a second door onto the same command, and the top bar is the
wrong place for a per-document field.

Declaring a model is therefore just editing a field, and Phase 5's declare-model row
needs no bespoke seam: it navigates to `Header` and reveals `Model` through the same
`reveal-missing-alias` / `navigate` seams every other Outstanding row uses (see
decision L). The `Header`-absent precondition that motivated the chip's own gate is
handled upstream and unchanged: when `Header` is missing, `document_completion` emits
`MISSING_SECTION ("Header",)` rather than `DECLARE_MODEL`, so no UI path reaches
`ChangeModel` on a Header-less document and `editing._navigate`'s `EditError`
(editing.py:23-36) stays unreachable from the UI.

**Consequence for decision C (see its own caveat):** the declare-model row can only
reveal Model's suggestion row if Header's "fields to add" group survives the
undeclared-model suppression — hence C's Header exemption.

### Phase 5 — Validation page: Outstanding section + absorption + badge
Decisions E, F, G, L, and the pinned copy. Consumes Phase 2's `partition_issues` —
`main_window._refresh_all` (main_window.py:769-786) switches both
`self._validation.refresh(...)` and the rail `set_badge(...)` to its output instead of
today's pre-absorption `document.error_count`/`warning_count`, so panel and badge are
one derivation by construction. Absorption facts already verified: attachment-level
matching (V4), clean union locs (V3), two-diagnostic null absorption (V5).
**Outstanding activation is polymorphic** — decision L names four distinct actions,
but `ValidationPanel.issue_activated` today is a single navigate-only
`Signal(tuple)` (validation_panel.py:31). The Outstanding section needs an
action-typed activation signal (navigate / reveal-missing-alias via Phase 3's seam /
AddSection / open set-model chooser); do not force these through NavigationService,
which cannot address non-existent targets. Drive the real app through mockup states
1–4 (skeleton / working doc / Partial / complete) and compare against the mockup.

Docs owed as phases land (code-first): `03-features.md` §5/§8 (completion architecture
→ stateless projection; Validation page two-section layout; absorption rule);
`02-ui.md` (parameter-list group, page layout, badge meaning); `04-roadmap.md` (list
this track — it currently omits it entirely). `PROJECT_STATUS.md` after every phase.

---

## 4b. Amendment 2026-07-16 — Validation page rail redesign (user-approved)

The user reviewed the shipped two-section page and reopened **decision F only**
(design workflow: three concepts → section-rail chosen → refined wireframe signed
off, incl. v2 revisions). Every other locked decision (B, C, D, E, G, H–R, pinned
copy) stands. New locked decisions:

> **Naming note (2026-07-16, separate task):** the page was renamed **Diagnostics**
> across the app (working tree). "Validation page" in this plan = the Diagnostics
> page. The BPX data *section* named `Validation` keeps its name everywhere.

| # | Decision |
|---|---|
| **F2** | **Page shape:** summary strip (error/warning/outstanding totals) + left section rail + single-section detail pane replaces the stacked Issues/Outstanding page. The pane shows the selected section's Issues box above its Outstanding box (banded group boxes). **"All sections"** rail entry = the unified whole-document view — each section exactly once, issues then outstanding under a foldable header (pinned copy verbatim there) — and is the **default on open**. In-pane box headers adapt: `Outstanding · N of M remaining` / `· section absent` (section name implicit). |
| **F3** | **Nothing is lost (test-enforced):** every diagnostic/task lands in exactly one rail bucket — display section when the path resolves, else nearest existing ancestor (existing orphan rule), else a **Document** bucket (rail entry that exists only while occupied). Rail entries derive from schema sections ∪ raw top-level keys ∪ diagnostic-bearing buckets, so unknown top-level sections get entries. All-sections renders the entire partition unfiltered (the backup view). Regression test: strip totals = Σ rail badges = All-sections rows = app-rail badge, post-absorption. |
| **F4** | **Quiet rail:** badges only where something needs attention (red = post-absorption issues, grey = outstanding; absent section = italic name + grey badge). **No ✓ / no zero** — quiet ≠ "complete" (a valid section may still have optional fields to add; that offer stays in the parameter list). Pane empty states keep the pinned ✓ wording. |
| **F5** | **Severity icons** (red ✕ circle / amber !) replace the `[ERROR]`/`[WARN]` text tags on issue rows; task glyphs stay ○ missing / ◐ added-no-value. Row anatomy otherwise unchanged (bold location + muted unit; verbatim message muted on line 2; REQUIRED tag; action text always visible, right-aligned). Activation contract L unchanged; rail click/arrows switch the pane (selection never mutates); rail selection + fold state persist per session. Document-bucket rows navigate to their attachment point; no attachment → no-op. |
| **F6** | **Multi-document (user ruling, 2026-07-16): the Validation page exists only for the main/primary document.** The panel still binds to one DocumentSession with per-session view state and no module-level view globals, but no per-document validation views, switchers, or cross-document comparison are ever owed. Nothing speculative built. |
| **F7** | **Phasing:** phase A = strip + rail + pane + All-sections + F3 reconciliation test (this amendment); later phases (separately approved): chips-as-filters, text filter. Verification per design workflow: headless AppDriver tests + real-app screenshot against the signed-off wireframe. |
| **F8** | **Filter semantics (phase B, user said "proceed" 2026-07-17; details are provisional defaults, copy flagged for sign-off):** filters are **view-only** — rail badges, strip counts, app badge, and all F3 reconciliation stay unfiltered truth; filtering hides rows, never re-counts them. Each strip chip is an independent toggle, all ON by default; toggling OFF hides that category's rows in the detail pane and All-sections view (error/warning chips → issue rows by severity; outstanding chip → task rows). Off chips render visibly muted/pressed-out. Text filter: field on the strip (right side), live case-insensitive substring match against row location/name text and message text; Esc clears; applies on top of chip filters. When any rows are hidden in the current view, a single quiet muted line renders at the view's end: `N hidden by filters` (new copy, flagged) — hidden-by-filter must never read as resolved. Fold state and filters compose (a fold hides its group's rows independently). Filter state is per-session view state (F6 discipline), resets on new document. Activation/keyboard contracts unchanged; arrow keys skip hidden rows trivially since hidden rows are not built. |

Docs owed when this lands: `02-ui.md` + `03-features.md` §5 page-layout text
(two-section description → rail design).

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
  hunting: under a concrete model, every Required absence is visible either as a
  "fields to add" entry or an Outstanding row — including the states where the
  validator itself goes blind (V1's Cell suppression, absent sections). Under an
  undeclared model the one visible task is "declare a model" (decision C suppresses
  every other section's suggestions, deliberately — but not `Header`'s own, which is
  where that task is carried out); under Partial, suggestions show but nothing is
  Required.
- Red means wrong, never unstarted — **in the Outstanding section and the rail
  badge**: nothing the app itself wrote (a scaffolded section, a `null` from `+`)
  ever counts as an error *there*. The parameter's own inline badge and row marker
  still mirror the validator verbatim, per decision D — do not suppress them.
- The validator is never silenced — every diagnostic is visible on the page, in
  exactly one of the two sections.
- All five phases landed as separate commits; docs match the app; the full suite is
  green with the new unit and driver tests.
