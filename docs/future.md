# Explore_BPX — Future ideas

Speculative ideas and unresolved decisions that are **not accepted design**.
Nothing here is an implementation requirement; an idea graduates only by
being designed, agreed and moved into [architecture.md](architecture.md).

## Data sources and import

Further BPX sources — LiionDB is the concrete candidate — behind source
adapters returning raw BPX dictionaries, modelled on `bpx_gateway.py`. The
pattern is proven: the bundled example and reference libraries are two
shipped adapters of exactly this shape. A converted external set is a
reference artifact, not a simulation-grade substitute — only a subset of
parameters maps into BPX, and each generated file says so in its own
Description.

## Export and simulator integration

Simulator hand-off (e.g. PyBOP, PyProBE) via target-specific writers behind
`core/export.py`, plus compatibility checks where appropriate.

## Multi-document Workspace

The accepted Workspace philosophy — one Primary, optionally one read-only
Reference, comparison as an editor capability — is in
[architecture.md](architecture.md). The interactive multi-document phase
remains future work:

- a `Workspace` state object holding Primary and Reference sessions,
  introduced only once a consumer exists;
- comparison rendering: a shared tree with ownership indicators (never
  filtering), dual inspectors, copying values between documents, difference
  highlighting, old/new value review;
- open design questions: adding and deleting parameters during comparison,
  copy semantics across incompatible structures, comparing different model
  types, validation behaviour while comparing, and nodes present on one side
  only.

## Authoring extensions

Organisation-, lab- or chemistry-specific templates; session change awareness
(a diff against the last loaded/saved baseline, with modified indicators and
a Changes view navigating through `NavigationService`); authoring states
beyond present/missing; provenance and confidence tracking; review workflows
for template-derived values; reusable parameter packs.

## Plausibility validation

Sanity checks against known or typical cell parameter ranges, as a separate
validation layer with its own versioned reference dataset — independently
sourced and tested, and never added to `bpx_gateway.py`, keeping schema
validation and domain plausibility distinct concerns.

## Search

Ranking, type markers, recent searches; searching validation issues,
comparison results and database references through the same navigation
surface.

## Analysis and visualisation

An **Analysis** tab in the Inspector's secondary workspace — the next piece
of design work, and it requires its own design pass before any UI is built.
Beyond it: plausibility displays against reference data, comparison overlays
for related files or known cells, and docking or maximising floating plots
if they need more space.

## ParameterTool protocol

When a second Inspector tool ships, evolve `SecondaryWorkspace` toward a
small `ParameterTool` protocol (`id`, `title`, `supports()`, `update()`) so
tools register generically instead of each needing bespoke wiring. The
abstraction should be derived from two real examples, not invented for one.
