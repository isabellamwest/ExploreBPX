# Explore_BPX — Future

This document collects speculative ideas and unresolved decisions that are **not
yet accepted design**. Nothing here is an implementation requirement. Items here
must never influence implementation until they are explicitly promoted into the
specification ([00-project.md](00-project.md) through [04-roadmap.md](04-roadmap.md)).

Promotion means: the idea is designed, accepted, and moved into the owning
specification document, with any implementation sequencing added to
[04-roadmap.md](04-roadmap.md). Until then, treat everything below as exploratory.

## Data sources and import

- LIIONDB import.
- Other BPX database sources.
- Additional source adapters implemented as anti-corruption layers that return raw
  BPX dictionaries, mirroring `bpx_gateway.py`.

### Bundled PyBaMM parameter sets as a reference library

Suggested externally (2026-07): ship a small, read-only library of well-known
parameter sets (Chen2020, Marquis2019, …), converted from PyBaMM into BPX, so a
user can pull one up as a **reference for comparison and plotting**. This is the
concrete first candidate for the "other BPX database sources" bullet above and a
natural source of Reference documents for the future Workspace.

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

- Simulator hand-off targets such as PyBOP and PyProBE.
- Target-specific writers behind the export layer.
- Simulator compatibility checks where appropriate.

## Workspace and multi-document support

The accepted **Workspace** philosophy — the application edits a Workspace of one
Primary and optionally one Reference document, and comparison is a capability of
the Editor rather than a separate mode — lives in [00-project.md](00-project.md)
and [01-architecture.md](01-architecture.md). The items below are the **future
design work** that follows from it. They are intentionally unresolved and must not
influence implementation until the multi-document phase becomes an active
milestone.

- A `Workspace` state object holding the Primary and an optional Reference
  `DocumentSession`, introduced only when multi-document work begins — never as a
  speculative container before a consumer exists.
- The **Workspace page** (activity-bar sibling to Editor and Validation):
  document- and workspace-level information and management — title, description,
  references, BPX version, model, Primary/Reference details, recent documents and
  new-document actions.
- **Contextual launch:** opening onto the Workspace page on a cold start (no
  document, recent or file argument) and straight into the Editor when opening or
  resuming a file.
- The **contextual toolbar:** exposing the current activity-bar page's actions
  rather than a fixed global set, with Open becoming a Workspace action. Its
  design must reconcile its relationship with the top context bar and the friction
  of opening a second file from the Editor.

## File comparison

Comparison is rendered by the Editor when a Reference document is present —
components render the Workspace (one or two documents) rather than switching into
a compare mode. The following are future design items, each requiring dedicated
UX work:

- Shared/merged tree rendering with ownership **indicators** (never ownership
  filtering of the structure; see the filtering rule in [02-ui.md](02-ui.md)).
- Dual parameter inspectors showing both documents' cards side by side.
- Copying values and structures between documents.
- Grouped issues and grouped or overlaid analysis across both documents.
- Difference highlighting.
- Old/new value display and review before save or export.
- Template comparison and last-export comparison.

### Open design questions (multi-document phase)

These are significant UX problems to be designed in the multi-document phase, not
solved now:

- Adding parameters during comparison.
- Deleting parameters during comparison.
- Copy semantics, including copying incompatible structures.
- Comparing different BPX model types.
- Validation behaviour during comparison.
- Behaviour when one document contains nodes the other does not.

## Parameter documentation — educational metadata source

The scheduled parameter information popover ([04-roadmap.md](04-roadmap.md)) starts
from `FieldMeta`. Richer educational metadata — physical meaning, measurement
methods, BPX specification links, symbols and equations — is not exposed by the
`bpx` package and would come from a separate, versioned reference dataset layered
over `bpx_gateway.py`, sourced and tested independently and never contaminating
the BPX gateway (mirroring the plausibility-dataset discipline). The dataset
itself is future work; the popover ships first against available `FieldMeta`.

## Authoring — speculative extensions

These extend the accepted Authoring feature ([03-features.md](03-features.md)) but
are not yet designed:

- Organisation-, lab-, chemistry- or workflow-specific templates.
- Session change awareness derived from comparison with the last loaded or saved
  baseline — answering what differs from the baseline rather than what actions the
  user performed.
- Subtle modified indicators in the existing editing UI (Tree, Parameter list,
  Inspector) that do not compete with validation colours.
- A dedicated Changes workspace summarising Modified, Added and Deleted items and
  navigating to affected locations through `NavigationService`.
- Parameter authoring states beyond present/missing values.
- Provenance and confidence tracking.
- Review/confirmation workflows for template-derived values.
- Reusable parameter packs.

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

- Ranking.
- Icons or type markers.
- Recent searches.
- Searching validation issues, comparison results or database references through
  the same navigation surface.

## Analysis and visualisation — extensions

- Parameter-centric plausibility displays using reference datasets.
- Docking or maximising floating visualisations if plots need more space.
- Comparison overlays for related files or known cells.

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
