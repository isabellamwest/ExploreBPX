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
- **Phase 1** is complete, as are items **2.1** and **2.2**. **2.3** is the
  immediate next work. Later phases depend on earlier ones.
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
| Validation workspace and parameter-scoped Issues tab | [Validation](03-features.md#5-validation) |
| Export / round-trip JSON or YAML | [Save and Export](03-features.md#7-save-and-export) |
| Dirty / backing-file state | [Save and Export](03-features.md#7-save-and-export) |
| Distinct Save vs Export semantics | [Save and Export](03-features.md#7-save-and-export) |
| Single `NavigationService` navigation coordinator | [01-architecture.md](01-architecture.md) |
| SearchPopup navigation over objects and parameters | [Search](03-features.md#6-search) |
| `DocumentSession` / `AppState` split | [01-architecture.md](01-architecture.md) |
| Raw-dict model and incomplete scaffolds | [Authoring](03-features.md#8-authoring) |

## Phase 2 — Navigation, review and file semantics

This phase completes the interaction foundation the later feature work relies on.

### 2.1 SearchPopup navigation

- **Status:** Implemented.
- **Depends on:** `NavigationService` (Phase 1).
- **Acceptance criteria:**
  - search is focused by `Ctrl+F` and `Ctrl+P` and selects existing text;
  - the SearchPopup indexes objects and parameters and shows name over path;
  - Up/Down, Enter and staged Escape behave as specified;
  - every result activation goes through `NavigationService`;
  - search never hides tree nodes or parameter rows.
  - See [Search](03-features.md#6-search).

### 2.2 Distinct Save vs Export semantics

- **Status:** Implemented.
- **Depends on:** dirty/backing-file state (Phase 1).
- **Acceptance criteria:**
  - Save writes back to the current backing file and clears Modified;
  - Export writes a copy without changing Modified;
  - the status bar reflects the resulting state.
  - See [Save and Export](03-features.md#7-save-and-export).

### 2.3 Keyboard navigation in the Validation workspace and Issues tab

- **Depends on:** validation issue mapping and `NavigationService` (Phase 1).
- **Acceptance criteria:**
  - arrow keys select rows in the issue list (native list behaviour);
  - Enter/Return activates the selected issue through `NavigationService`;
  - selection change alone does not navigate — arrow to survey, Enter to commit;
  - focus stays in the list after activation, so the user can arrow to the next
    issue and Enter again;
  - the parameter-scoped Issues tab gets the same behaviour.
  - See [Validation](03-features.md#5-validation).

### 2.4 Parameter information popover and self-contained ParameterCard

- **Depends on:** nothing beyond Phase 1. Independent of Workspace and
  multi-document support.
- **Acceptance criteria:**
  - a contextual BPX parameter information popover ( i ) is available on every
    ParameterCard, opened from the card and dismissed by a second ( i ) click or
    Escape;
  - the popover surfaces rich BPX metadata (physical meaning, units, accepted
    types, functional dependence, model availability, measurement methods,
    specification links, symbols) from a unified parameter-metadata provider that
    combines `FieldMeta` with a separate educational-metadata source;
  - as supporting work, the ParameterCard becomes self-contained — the parameter
    title, validity badge and summary description move into the card — while the
    existing editing/commit contract is unchanged;
  - parameter documentation is not added as a secondary-workspace tab.
  - See [Parameter Inspection](03-features.md#3-parameter-inspection).

## Phase 3 — Authoring foundation

Authoring is a priority track and begins as soon as the interaction foundation is
in place. The one open design question it depended on — user-defined parameter
metadata — is resolved (3.0, below).

### 3.0 User-defined parameter metadata — resolved (`meta=None` contract)

- **Status:** Resolved. A user-authored custom parameter is an ordinary
  raw-dict entry whose `FieldMeta` is genuinely absent (`meta=None`). Nothing
  is synthesised and nothing is persisted for it. `classify` stays
  metadata-authoritative wherever metadata exists and falls back to
  value-shape classification where it is absent; absence is a valid
  first-class state, and the BPX validator is the source of truth for whether
  a custom parameter is legal. See [01-architecture.md](01-architecture.md).
- **Depends on:** nothing; it was a design decision.
- **Acceptance criteria:**
  - the `meta=None` contract is locked by tests (valueless custom parameter →
    `UNKNOWN`; numeric → `SCALAR`; string → `FUNCTION`; a known alias still
    resolves its `FieldMeta` and remains metadata-authoritative);
  - no runtime behaviour change — `classify` already implemented this.
- **Note:** because no persistence mechanism exists or is needed, the
  authoring capabilities that create parameters (4.4's raw/unknown fallback
  editor, and the add-parameter workflows below) are built as general
  "metadata-absent" capabilities rather than against any specific synthesis
  mechanism, so broader custom-parameter authoring remains feasible later
  without rework.

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

- **Status:** Implemented (`RawCard`; `UNKNOWN`-kind parameters route to an editable
  raw card instead of the read-only dead end; a committed value reclassifies to its
  real kind on rebuild).
- **Depends on:** nothing beyond Phase 1.
- **Acceptance criteria:** parameters with no known kind are still editable through
  a raw fallback. See [Editing](03-features.md#4-editing).

### 4.5 Add custom parameter (freeform)

- **Status:** Implemented (section-scoped "+ Add parameter" header on the
  parameter-list pane opens a popup with a "Create custom parameter" row; routes
  through the `AddParameter` command with an empty value and reveals via
  `NavigationService`).
- **Depends on:** 4.4 (raw/unknown fallback editor); 3.0 (`meta=None` contract,
  resolved).
- **Acceptance criteria:**
  - the user can add a freeform custom parameter (key and value) to a section;
  - the new entry is an ordinary raw-dict entry — no `FieldMeta` is
    synthesised or persisted for it;
  - it renders through the 4.4 raw/unknown fallback editor, or a more specific
    kind if its value shape resolves one, exactly as `classify` already
    handles `meta=None`;
  - the BPX validator remains the sole judge of whether the custom parameter
    is legal BPX content — nothing is fabricated to make it look schema-known.
  - See [Authoring](03-features.md#8-authoring).

### 4.6 Add BPX parameter (searchable picker)

- **Status:** Implemented as one unified surface with 4.5. The same add-parameter
  popup lists a section's expected aliases (via `expected_fields`) on empty input
  and, on search, filters those (shown emphasised) while also surfacing other
  matching BPX aliases from `metadata_index()` (shown greyed). Known limitation:
  electrode sections cannot enumerate expected fields (the single/blended union
  needs live content), so they show no expected suggestions — search still surfaces
  full-schema aliases, and custom-add still works.
- **Depends on:** 4.4 (raw/unknown fallback editor); UI design for the picker
  ([02-ui.md](02-ui.md), amended to specify the parameter-list add surface).
- **Acceptance criteria:**
  - the user can search known BPX schema aliases and add one not yet present
    in the document;
  - the added parameter resolves its `FieldMeta` from `metadata_index()`
    (metadata-authoritative), not from synthesis;
  - picker UI/UX is designed in [02-ui.md](02-ui.md) before implementation.
  - See [Authoring](03-features.md#8-authoring).

## Phase 5 — Actionable validation

### 5.1 `IssueKind` and remediation functions

- **Depends on:** the Validation workspace and issue mapping (Phase 1).
- **Acceptance criteria:**
  - issues carry an `IssueKind` describing implied remediation;
  - pure remediation functions in `core/` take an issue and raw dict and return a
    proposed fixed dict;
  - warnings that currently land at the document root regain usable field paths.
  - See [Validation](03-features.md#5-validation).

## Phase 6 — Analysis and visualisation

### 6.1 Inspector analysis tab (design then build)

- **Depends on:** the Inspector secondary-workspace mechanism (Phase 1).
- **Note:** this feature is intentionally underspecified and requires a design pass
  before implementation (see [Analysis and Visualisation](03-features.md#9-analysis-and-visualisation)).
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
