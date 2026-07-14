# Explore_BPX — Roadmap

This document defines **remaining implementation work only**: what is not yet
built, the dependencies between items, and the acceptance criteria for each.

It contains no architecture and no UI or feature design. Those are owned by
[01-architecture.md](01-architecture.md), [02-ui.md](02-ui.md) and
[03-features.md](03-features.md). Where an item needs behavioural detail, this
document links to the owning feature rather than restating it. Every capability
named here is defined, with its Implemented/Planned status, in
[03-features.md](03-features.md).

## Status

The editing and authoring foundation is complete: document loading (including
invalid and incomplete files), the derived object tree and parameter inspection,
editing across every parameter kind, command-based mutation with undo, structural
tree editing (add/remove sections; add/rename/remove materials and experiments),
continuous validation with a parameter-scoped Issues tab, search, authoring from
model skeletons, and save/export. The authoring/completion track has also landed:
a stateless completion query (`core/completion.py`) surfaces expected-but-missing
fields as a collapsed "N fields to add" group in the parameter list and as an
Outstanding section on the Validation page (alongside Issues, with validator
diagnostics already covered by an Outstanding task absorbed rather than
double-shown). A document declares or changes its model by editing
`Header.Model` in the Editor like any other field — the commit scaffolds the
new model's required sections in the same undo step. The capability matrices in
[03-features.md](03-features.md) carry the authoritative per-feature status.

The items below are the capabilities still marked Planned.

## Editing depth

### Enhanced function-expression editor

- **Depends on:** basic function editing (built).
- **Acceptance criteria:** syntax highlighting and expression validation for
  function fields. See [Editing](03-features.md#4-editing).

### Compact quick inputs in the parameter list

- **Depends on:** the parameter list and per-kind editors (built).
- **Acceptance criteria:** simple scalar/enum values are editable inline in the
  parameter list without opening the Inspector card. See
  [Parameter Inspection](03-features.md#3-parameter-inspection).

## Actionable validation

### `IssueKind` and remediation functions

- **Depends on:** the Validation workspace and issue mapping (built).
- **Acceptance criteria:**
  - issues carry an `IssueKind` describing implied remediation;
  - pure remediation functions in `core/` take an issue and raw dict and return a
    proposed fixed dict;
  - warnings that currently land at the document root regain usable field paths.
  - See [Validation](03-features.md#5-validation).

## Analysis and visualisation

### Inspector analysis tab (design then build)

- **Depends on:** the Inspector secondary-workspace mechanism (built).
- **Note:** intentionally underspecified; requires a design pass before
  implementation (see [Analysis and Visualisation](03-features.md#9-analysis-and-visualisation)).
- **Acceptance criteria:**
  - Analysis is a tab in the Inspector secondary workspace over the selected
    parameter, acting as a launcher of per-tool `Show` actions rather than
    embedding large graphs;
  - function and interpolated-table parameters can be visualised in a floating
    view;
  - no analyzer registry is introduced before a concrete analyzer exists.

## Deferred to future

Recent documents, external database import, simulator hand-off, the
multi-document **Workspace** (Primary plus optional Reference) and comparison as
an Editor capability, the Workspace page, the contextual toolbar, contextual
launch, the educational parameter-metadata dataset, session change review,
plausibility validation and richer authoring metadata are not scheduled here.
They remain in [05-future.md](05-future.md) until promoted into the
specification.
