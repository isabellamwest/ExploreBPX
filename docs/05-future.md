# Explore_BPX — Future

This document collects speculative ideas and unresolved decisions that are **not
yet accepted design**. Nothing here is an implementation requirement. Items here
must never influence implementation until they are explicitly promoted into the
specification ([00-project.md](00-project.md) through [04-roadmap.md](04-roadmap.md)).

Promotion means: the idea is designed, accepted, and moved into the owning
specification document, with any implementation sequencing added to
[04-roadmap.md](04-roadmap.md). Until then, treat everything below as exploratory.

## Data sources and import

LIIONDB import and other BPX database sources, each as a source adapter
(anti-corruption layer returning raw BPX dictionaries, mirroring `bpx_gateway.py`).
**The pattern itself is now proven, not just proposed:** `core/example_library.py`
is a first, real adapter of this shape over a bundled About:Energy source (see
`01-architecture.md`'s Core Module Responsibilities and Extension Seams), feeding
the Validation-run "Compare…" dialog. A second source (LiionDB, or the
PyBaMM-derived library below) is another entry in its source list — see the
module for the exact seam.

### Bundled PyBaMM parameter sets as a reference library

Suggested externally (2026-07): ship a small, read-only library of well-known
parameter sets (Chen2020, Marquis2019, …), converted from PyBaMM into BPX, so a
user can pull one up as a **reference for comparison and plotting**. This is the
concrete first candidate for the "other BPX database sources" bullet above and a
natural source of Reference documents for the future Workspace. Unlike the
bundled-examples adapter above, a converted PyBaMM set has no Validation section
(PyBaMM parameter sets carry no cycling data) — it would need its own picker UI
built around Parameterisation comparison, not the run-comparison dialog that
already exists.

Feasibility has been checked on Chen2020 (converted to BPX, passes the `bpx`
validator, and round-trips back into PyBaMM). Findings that constrain any future
design — recorded so they are not rediscovered:

- **A converter is ours to own.** PyBaMM reads BPX (`create_from_bpx`) but has no
  official BPX *writer*; the PyBaMM → BPX direction is bespoke.
- **A converted set is a reference artifact, not a simulation-grade substitute.**
  Only a subset of parameters map: functions (OCP, electrolyte properties) become
  sampled interpolated tables, stoichiometry limits must be computed, the reaction
  rate constant is reconstructed, and degradation / current-collector / detailed
  thermal parameters have no BPX home. Each generated file should say so in its
  Description. Only DFN-shaped lithium-ion sets convert; MSMR and lead-acid do not.
- **Generation is offline, not a runtime dependency.** A dev-time tool (which may
  import PyBaMM) would emit validated static BPX files that the app loads as
  ordinary data; the application itself never imports PyBaMM, preserving the rule
  that BPX coupling lives only behind `bpx_gateway.py`.

Not accepted design. Promotion would require a UI design pass for how the library
is browsed and chosen, and agreement on which sets to include.

## Export and simulator integration

Simulator hand-off (e.g. PyBOP, PyProBE) via target-specific writers behind the
export layer, plus simulator compatibility checks where appropriate.

## Workspace and multi-document support

The accepted **Workspace** philosophy — one Primary and optionally one Reference
document, comparison as a capability of the Editor rather than a separate mode —
lives in [00-project.md](00-project.md) and [01-architecture.md](01-architecture.md).
Unresolved future design work, not to influence implementation until the
multi-document phase becomes an active milestone. **Not a precedent:** the
"Add database examples" dialog (`database_examples_dialog.py`) reads like an
early Workspace, but deliberately is not one — it holds a plain, disposable,
read-only snapshot with no `DocumentSession`, no undo, no persistence across
being closed. It does not validate any Workspace design question above; treat
it as a comparison *dialog*, not a scaled-down Workspace, until a second,
genuinely *interactive* multi-document consumer exists.

- A `Workspace` state object holding Primary and optional Reference
  `DocumentSession`, introduced only when multi-document work begins — never as a
  speculative container before a consumer exists.
- The **Workspace page** (activity-bar sibling to Editor and Diagnostics):
  document/workspace-level info and management (title, description, references,
  BPX version, model, Primary/Reference details, recent documents, new-document
  actions).
- **Contextual launch:** Workspace page on cold start, straight into the Editor
  when opening or resuming a file.
- The **contextual toolbar:** current activity-bar page's actions rather than a
  fixed global set, with Open becoming a Workspace action; must reconcile with
  the top context bar and the friction of opening a second file from the Editor.
- Comparison rendering (shared/merged tree with ownership indicators — never
  filtering, see [02-ui.md](02-ui.md)), dual parameter inspectors, copying values
  between documents, grouped/overlaid issues and analysis, difference
  highlighting, old/new value review, template and last-export comparison.

### Open design questions (multi-document phase)

These are significant UX problems to be designed in the multi-document phase, not
solved now:

- Adding parameters during comparison.
- Deleting parameters during comparison.
- Copy semantics, including copying incompatible structures.
- Comparing different BPX model types.
- Validation behaviour during comparison.
- Behaviour when one document contains nodes the other does not.

## Authoring — speculative extensions

Extend the accepted Authoring feature ([03-features.md](03-features.md)), not yet
designed: organisation/lab/chemistry/workflow-specific templates; session change
awareness (diff against last loaded/saved baseline, not user actions) with subtle
modified indicators in Tree/Parameter list/Inspector and a dedicated Changes
workspace navigating via `NavigationService`; parameter authoring states beyond
present/missing; provenance and confidence tracking; review/confirmation
workflows for template-derived values; reusable parameter packs.

## Validation — plausibility layer

- Plausibility / sanity validation against known or typical cell parameter ranges.
- Implemented as a separate validation layer with its own versioned reference
  dataset (for example `core/sanity.py`), sourced and tested independently of
  schema validation, and never added to `bpx_gateway.py`.

This is a distinct concern from BPX schema validation and requires a reference
dataset of domain knowledge. It is recorded as a future architectural
consideration: schema/syntax validation and plausibility validation must remain
independently sourced and independently testable.

## Search — richer results

Ranking, icons/type markers, recent searches, and searching validation issues,
comparison results or database references through the same navigation surface.

## Analysis and visualisation — extensions

Parameter-centric plausibility displays using reference datasets; docking or
maximising floating visualisations if plots need more space; comparison overlays
for related files or known cells.

## Inspector secondary workspace — ParameterTool protocol

When a second concrete tool is ready (Analysis, References, etc.),
`SecondaryWorkspace` should evolve toward a `ParameterTool` protocol so tools
register generically without requiring Inspector-specific wiring each time:

```python
class ParameterTool:
    id: str
    title: str
    def supports(self, parameter) -> bool: ...
    def update(self, parameter) -> None: ...
```

`SecondaryWorkspace` would route `show_parameter` calls to all registered tools
and surface each tab only when `supports()` returns True. Do not build this before
a second concrete tool is ready — the abstraction should be derived from two
examples, not invented for one.
