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

## Export and simulator integration

- Simulator hand-off targets such as PyBOP and PyProBE.
- Target-specific writers behind the export layer.
- Simulator compatibility checks where appropriate.

## Workspace and multi-document support

- Multiple open document sessions over `DocumentSession`.
- Workspace/library management.
- An active-document switcher UI.
- Comparison navigation between documents.

## File comparison

- Multiple `DocumentSession` objects plus tree-model diffing and shared
  navigation.
- Old/new value display, filtering and review before save or export.
- Template comparison and last-export comparison.

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
- An optional maximised Inspector section if plots need more space.
- Comparison overlays for related files or known cells.

## Reference — superseded design register

The project previously kept a numbered Design Decision register (DD-001 through
DD-012) in the UI document. Those decisions have been promoted into the documents
that own their subject matter, embedded inline as design rationale:

- Workspace shell, activity bar, secondary surfaces, toolbar shape → [02-ui.md](02-ui.md).
- DocumentSession/AppState split, navigation ownership → [01-architecture.md](01-architecture.md).
- Editing commit model, validation review and cursor behaviour, parameter-scoped
  Issues drawer, SearchPopup, Save/Export semantics → [03-features.md](03-features.md).

The one decision that was still **Proposed** — the BPX authoring lifecycle
(formerly DD-012) — has since been accepted as a core product commitment and is now
part of [00-project.md](00-project.md), [01-architecture.md](01-architecture.md) and
the Authoring feature in [03-features.md](03-features.md). No separate decision
register is maintained; this note exists only to explain the history for anyone
looking for the old DD numbers.
