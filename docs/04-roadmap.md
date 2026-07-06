# Explore_BPX — Roadmap

This document defines **implementation order only**: what is already built, what
comes next, the dependencies between items, and the acceptance criteria for each
planned item.

It contains no architecture and no UI or feature design. Those are owned by
[01-architecture.md](01-architecture.md), [02-ui.md](02-ui.md) and
[03-features.md](03-features.md). Where an item needs behavioural detail, this
document links to the owning feature rather than restating it. Every capability
named here is defined, with its Implemented/Planned status, in
[03-features.md](03-features.md).

## How to read this roadmap

- Items are grouped into phases by dependency, not by release number.
- **Phase 1** is complete. **Phase 2** is the immediate next work. Later phases
  depend on earlier ones.
- Editing and Authoring are the two priority tracks and are sequenced to advance
  together, consistent with the accepted product principles in
  [00-project.md](00-project.md).
- Acceptance criteria are the observable conditions that mark an item done. They
  are derived from the capability matrices in [03-features.md](03-features.md).

## Phase 1 — Implemented foundation

The following capabilities are built and form the current application. They are
listed here only to establish the baseline that later phases depend on.

| Capability | Owning feature |
|---|---|
| Open JSON/YAML BPX files, including invalid/incomplete ones | [Document Loading](03-features.md#1-document-loading) |
| Import menu (Open File) | [Document Loading](03-features.md#1-document-loading) |
| Derived object tree and object selection | [Tree Navigation](03-features.md#2-tree-navigation) |
| Parameter list and Inspector detail | [Parameter Inspection](03-features.md#3-parameter-inspection) |
| Declared-type-first parameter classification | [Parameter Inspection](03-features.md#3-parameter-inspection) |
| Scalar, integer, enum and basic function editing | [Editing](03-features.md#4-editing) |
| Enter-to-commit / Escape-to-revert model | [Editing](03-features.md#4-editing) |
| Command-based mutation with undo | [Editing](03-features.md#4-editing) |
| Continuous BPX validation and `ValidationIssue` records | [Validation](03-features.md#5-validation) |
| Validation workspace and parameter-scoped Issues drawer | [Validation](03-features.md#5-validation) |
| Export / round-trip JSON or YAML | [Save and Export](03-features.md#7-save-and-export) |
| Dirty / backing-file state | [Save and Export](03-features.md#7-save-and-export) |
| `DocumentSession` / `AppState` split | [01-architecture.md](01-architecture.md) |
| Raw-dict model and incomplete scaffolds | [Authoring](03-features.md#8-authoring) |

## Phase 2 — Navigation, review and file semantics

This phase completes the interaction foundation the later feature work relies on.

### 2.1 SearchPopup navigation

- **Depends on:** `NavigationService` (Phase 1).
- **Acceptance criteria:**
  - search is focused by `Ctrl+F` and `Ctrl+P` and selects existing text;
  - the SearchPopup indexes objects and parameters and shows name over path;
  - Up/Down, Enter and staged Escape behave as specified;
  - every result activation goes through `NavigationService`;
  - search never hides tree nodes or parameter rows.
  - See [Search](03-features.md#6-search).

### 2.2 Distinct Save vs Export semantics

- **Depends on:** dirty/backing-file state (Phase 1).
- **Acceptance criteria:**
  - Save writes back to the current backing file and clears Modified;
  - Export writes a copy without changing Modified;
  - the status bar reflects the resulting state.
  - See [Save and Export](03-features.md#7-save-and-export).

### 2.3 Non-modal validation review cursor

- **Depends on:** validation issue mapping and `NavigationService` (Phase 1).
- **Acceptance criteria:**
  - the review cursor appears in the top context/mode bar and the editor stays
    interactive;
  - the cursor provides Previous, current number/total, current path, Next and
    Finish Review;
  - resolving the current issue keeps the cursor in place and shows a resolved
    state; it does not auto-advance;
  - resolved state and counts track committed document state, not live preview;
  - clicking a Validation workspace issue navigates and positions the cursor.
  - See [Validation](03-features.md#5-validation).

## Phase 3 — Authoring foundation

Authoring is a priority track and begins as soon as the interaction foundation is
in place. This phase depends on resolving one open design question first.

### 3.0 Resolve user-defined parameter metadata gap (design)

- **Depends on:** nothing; it is a design decision.
- **Blocks:** any authoring capability that creates parameters (section
  add/remove, skeletons, templates).
- **Acceptance criteria:**
  - a mechanism for persisting and looking up metadata for Explore_BPX-authored
    parameters is designed and accepted;
  - the mechanism keeps `classify` metadata-authoritative for authored
    parameters.
  - See the open gap in [01-architecture.md](01-architecture.md).

### 3.1 New BPX from model skeletons

- **Depends on:** 3.0; `document_factory.py` (Phase 1).
- **Acceptance criteria:**
  - the user can create a new document for SPM, SPMe, DFN and Partial;
  - skeletons contain structure only and no invented scientific values;
  - the new document opens in the normal Editor workflow.
  - See [Authoring](03-features.md#8-authoring).

### 3.2 Completion state distinct from validation

- **Depends on:** 3.1.
- **Acceptance criteria:**
  - completion status is tracked and displayed separately from validation status;
  - a completion view lists unfinished required authoring work;
  - completion navigation uses `NavigationService`;
  - no authoring/completion state forces values into exported BPX.
  - See [Authoring](03-features.md#8-authoring).

### 3.3 Expected-but-missing parameter rows

- **Depends on:** 3.0, 3.2.
- **Acceptance criteria:**
  - expected-but-missing parameters appear as editable rows in the editing
    workflow;
  - committing a row writes a real BPX value; leaving it does not.
  - See [Authoring](03-features.md#8-authoring).

### 3.4 Templates

- **Depends on:** 3.1.
- **Acceptance criteria:**
  - Save as Template and New from Template workflows exist;
  - templates may be skeletons or partially completed documents;
  - template-derived values remain honest BPX data on export.
  - See [Authoring](03-features.md#8-authoring).

## Phase 4 — Editing depth

These items extend editing to the remaining parameter kinds and structural
operations. They can proceed in parallel with Phase 3 where they do not depend on
authored-parameter metadata.

### 4.1 Enhanced function-expression editor

- **Depends on:** basic function editing (Phase 1).
- **Acceptance criteria:** syntax highlighting and expression validation for
  function fields. See [Editing](03-features.md#4-editing).

### 4.2 Editable table grid

- **Depends on:** nothing beyond Phase 1.
- **Acceptance criteria:** interpolated tables are editable as a grid and commit
  through the standard command/raw-dict path. See
  [Editing](03-features.md#4-editing).

### 4.3 Section add/remove and model-switch handling

- **Depends on:** 3.0 (authored-parameter metadata).
- **Acceptance criteria:** sections can be added/removed and structural model
  changes are handled through the command layer. See
  [Editing](03-features.md#4-editing).

### 4.4 Unknown/raw fallback editor

- **Depends on:** nothing beyond Phase 1.
- **Acceptance criteria:** parameters with no known kind are still editable through
  a raw fallback. See [Editing](03-features.md#4-editing).

## Phase 5 — Actionable validation

### 5.1 `IssueKind` and remediation functions

- **Depends on:** the review cursor (2.3).
- **Acceptance criteria:**
  - issues carry an `IssueKind` describing implied remediation;
  - pure remediation functions in `core/` take an issue and raw dict and return a
    proposed fixed dict;
  - warnings that currently land at the document root regain usable field paths.
  - See [Validation](03-features.md#5-validation).

## Phase 6 — Analysis and visualisation

### 6.1 Inspector analysis section (design then build)

- **Depends on:** the Inspector section mechanism (Phase 1).
- **Note:** this feature is intentionally underspecified and requires a design pass
  before implementation (see [Analysis and Visualisation](03-features.md#9-analysis-and-visualisation)).
- **Acceptance criteria:**
  - Analysis is an expandable/collapsible Inspector section over the selected
    parameter;
  - function and interpolated-table parameters can be visualised;
  - no analyzer registry is introduced before a concrete analyzer exists.

## Deferred to future

Recent documents, external database import, simulator hand-off, multi-document
workspaces, comparison, session change review, plausibility validation and richer
authoring metadata are not scheduled here. They remain in
[05-future.md](05-future.md) until promoted into the specification.
