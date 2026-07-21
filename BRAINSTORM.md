# Explore_BPX — Brainstorm

An idea pool for what the app could do next. **Nothing here is accepted design.**
Ideas get pulled from here into a PLAN (or into `docs/05-future.md` once promoted);
they never influence implementation directly. Statuses:

- `[active]` — has a locked PLAN, in progress
- `[chosen]` — concept picked, awaiting sign-off / implementation
- `[approved]` — design signed off, not started
- `[draft]` — plan written, awaiting review
- `[deferred]` — explicitly parked
- `[idea]` — raw brainstorm, undesigned

Effort guesses are rough: **S** (days), **M** (week-ish), **L** (multi-week).

---

## 1. Committed & in-flight tracks (for orientation)

- **Multi-file / source pane** `[chosen]` **L** — *the current main goal.*
  Concept B: one editable document + read-only source files docked as a fourth
  Editor pane; aligned rows, diff tinting, undoable pull. Nine decisions (D1–D9)
  drafted in the artifact "Multi-file support — Concept B decisions"; phasing
  B1→B4. Blocked on sign-off of the D-list.
- **Completion track** `[active]` — `PLAN-completion-track.md`.
- **Validation-section experiment card** `[approved]` — Concept C, decisions
  D1–D7, five phases.
- **Custom-parameter editing** `[chosen]` — Concept A shipped uncommitted;
  typed value-shape model, rename/move/duplicate.
- **App audit** `[active]` — `PLAN-app-audit.md`; Phase A done, on-screen walk next.
- **Database examples (Concept A)** `[approved]` — About:Energy NMC+LFP library,
  Compare… entry.

---

## 2. Multi-file — extensions beyond Concept B

Ideas that build on the source pane once B1–B4 exist. None are in scope for the
current track.

- **Second *editable* document** `[idea]` **L** — promote a source to a full
  `DocumentSession` (undo, dirty state, save) with an explicit "which file am I
  editing" switch. The Workspace tiles from D8 are the natural UI seat.
- **Pull in both directions / push** `[idea]` **M** — once two editable docs
  exist, "push this value to the other file". Same command shape as pull.
- **Bulk pull** `[idea]` **M** — "pull all missing parameters in this section"
  or "pull everything that differs", as one undo entry. Turns the pane into a
  real build-new-from-old tool.
- **Session restore / recent files** `[idea]` **S–M** — reopen last document +
  sources on launch; recent-documents list on the Workspace page (already in the
  accepted Workspace philosophy).
- **Whole-file diff summary** `[idea]` **M** — a Workspace-level "N parameters
  differ, M only in source" rollup per tile, computed with the same row-matching
  the pane already does. Cheap once B1 lands.
- **Template documents** `[idea]` **M** — "New from template": a bundled or
  user-saved skeleton opens as the editable doc with a chosen source pre-docked.

## 3. Model-fidelity lens (from the JES 2024 continuum-models schematic)

The schematic (JES **171** 100530, Fig. 1: Microscale → DFN → SPMe → SPM → RM)
frames models as a fidelity ladder. BPX's `Model` field already encodes three
rungs (DFN, SPMe, SPM), and `bpx` validates differently per rung — so all of
these route through the gateway, not hand-rolled field lists.

- **"What if this were SPM?" preview** `[idea]` **M** — revalidate the current
  document under a different `Model` value and show the resulting diagnostics
  before committing the switch. Pure gateway usage; zero invented spec logic.
- **Fidelity-readiness rollup** `[idea]` **M** — a small Workspace/Editor
  indicator: "valid as DFN; also valid as SPMe, SPM". Computed by the same
  revalidation trick; pairs naturally with the completion track's "what's
  missing" framing.
- **Model badge on source tiles** `[idea]` **S** — D8's tiles already show the
  model; extend with the fidelity ladder so mixing an SPM source into a DFN
  document is visibly a step *down* the ladder.
- **Downgrade-on-export** `[idea]` **M** — "Save a copy as SPM": write the file
  with `Model` switched, letting the validator (not us) say what breaks.
- **Ladder explainer** `[idea]` **S** — a small static visual (DFN → SPMe → SPM)
  in the Workspace or docs/about, for users who don't know the model families.
  Content-only; no spec logic.

## 4. Reference data & libraries

- **PyBaMM-derived reference sets** `[idea]` **M–L** — Chen2020, Marquis2019 …
  converted offline to static BPX files (feasibility already proven; converter is
  ours to own; no runtime PyBaMM import). With the multi-file pane these become
  first-class *sources* — the picker-UI problem noted in `docs/05-future.md`
  largely dissolves into "open as source".
- **LiionDB import** `[deferred]` **L** — second source adapter behind the
  `example_library` seam. Parked with the AI direction.
- **Plausibility / sanity layer** `[deferred]` **L** — range checks against a
  versioned reference dataset (`core/sanity.py`), forever separate from
  `bpx_gateway.py`. Parked; revisit after the active tracks.
- **User-contributed library folder** `[idea]` **S–M** — a watched local folder
  of the user's own BPX files surfaced alongside the bundled examples.

## 5. Visualisation & analysis

- **Function/table plot preview** `[idea]` **M** — plot an OCP curve or
  interpolated table from its card. Note the known gotcha: `matplotlib` is
  missing from the `.venv`; decide the plotting backend deliberately.
- **Comparison overlays** `[idea]` **M** — overlay a source's function/table on
  yours (two curves, one axes). The honest "semantic diff" for big kinds that D4
  deliberately excluded from phase 1.
- **Parameter-in-context displays** `[deferred]` — plausibility bands around a
  value; depends on the sanity layer's dataset.

## 6. Simulation & export

- **Simulator hand-off** `[idea]` **M–L** — export adapters for PyBaMM / PyBOP /
  PyProBE behind the export layer; possibly per-target compatibility notes.
- **Run preview** `[idea]` **L** — actually simulate (e.g. a C/2 discharge via
  PyBaMM) from the current file. Big dependency and scope question — likely an
  optional extra, never core. The fidelity ladder (§3) is the cheap sibling.
- **Validation report export** `[idea]` **S–M** — write the Diagnostics view to
  HTML/Markdown for sharing ("here's what's wrong with the file you sent me").
- **Headless CLI validate** `[idea]` **S** — `python -m explore_bpx validate *.json`
  reusing core only; useful for CI on parameter repositories.

## 7. Editing & authoring quality-of-life

- **Change awareness vs baseline** `[idea]` **M–L** — diff against last
  loaded/saved file (not the undo stack): modified indicators in Tree/list/
  Inspector plus a Changes view. Already sketched in the Authoring extensions.
- **Undo history panel** `[idea]` **S–M** — the command stack is already
  labelled; show it as a navigable list.
- **Provenance & confidence per value** `[deferred]` — sidecar recording where
  each value came from (typed, pulled from source X, template). Parked with the
  AI direction, but *pull* (D6) is quietly its first producer — worth keeping
  the command's metadata honest so provenance can attach later.
- **Richer search** `[idea]` **S–M** — ranking, type icons, recent searches;
  searching diagnostics and (later) sources through the same navigation surface.
- **Parameter packs** `[idea]` **M** — save a group of parameters (e.g. one
  electrode) for reuse; overlaps heavily with bulk pull + templates, so design
  them together, not separately.

## 8. AI-assisted (post-project direction, all deferred)

- **Gated AI extraction** `[deferred]` — extract candidate parameters from
  papers/datasheets into a *proposal* the user reviews; never writes directly.
- **LiionDB-backed plausibility prompts** `[deferred]` — see §4.
- No speculative scaffolding for any of this until the active tracks ship.

## 9. Housekeeping & infrastructure

- **App audit** `[active]` — already planned (`PLAN-app-audit.md`).
- **Docs reorganisation** — in progress, owned by Bella; the app remains the
  source of truth throughout.
- **Fix `.venv` matplotlib** `[idea]` **S** — either add it properly or remove
  whatever expects it; stop paying the "known gotcha" tax.
- **`ParameterTool` protocol** `[idea]` — extract only when a second concrete
  Inspector tool exists (rule already recorded in `docs/05-future.md`).

---

## Parking lot (unsorted sparks)

- Drag a JSON file onto the source pane to dock it directly.
- Copy a parameter as a JSON snippet / paste a snippet as a custom parameter.
- "Explain this diagnostic" links from the Diagnostics page to the relevant BPX
  docs section (content links only — never paraphrased spec logic).
- Per-document notes field (freeform scratch text saved outside the BPX file).
- Dark-mode / theming pass once the UI surface stabilises.
