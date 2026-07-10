# Explore_BPX — Features

This document is the authoritative specification for every feature of
Explore_BPX. It builds on the vision in [00-project.md](00-project.md), the
architecture in [01-architecture.md](01-architecture.md) and the UI framework in
[02-ui.md](02-ui.md).

Each feature is specified with one overview, one architecture, one workflow and
one capability matrix. **Status is tracked per capability**, always as one of two
values:

- **Implemented** — present in the current codebase.
- **Planned** — accepted design, to be built. Planned behaviour is the
  implementation target.

The implementation status of the whole application is derivable from these
capability matrices without inspecting the codebase. Implementation order and
acceptance criteria live in [04-roadmap.md](04-roadmap.md); speculative ideas live
in [05-future.md](05-future.md).

Each feature follows the same template: Overview, Capabilities, User Workflow, UI
Behaviour, Architecture, Dependencies, Implementation Notes, Design Rationale,
Future Extensions.

## Contents

1. [Document Loading](#1-document-loading)
2. [Tree Navigation](#2-tree-navigation)
3. [Parameter Inspection](#3-parameter-inspection)
4. [Editing](#4-editing)
5. [Validation](#5-validation)
6. [Search](#6-search)
7. [Save and Export](#7-save-and-export)
8. [Authoring](#8-authoring)
9. [Analysis and Visualisation](#9-analysis-and-visualisation)

---

## 1. Document Loading

### Overview

Loading brings a BPX file into the application as an editable document. It must
accept valid, invalid and incomplete files alike, because inspecting and
repairing broken files is a core purpose of the tool.

### Capabilities

| Capability | Status |
|---|---|
| Open JSON or YAML BPX files | Implemented |
| Open invalid and incomplete files as editable documents | Implemented |
| Import menu as the source hub (Open File) | Implemented |
| Recent documents | Planned |

### User Workflow

The user chooses Import → Open File and selects a `.json` or `.yaml` BPX file. The
file loads into the Editor workspace with its object tree, parameter list and
validation state populated. If the file is invalid, it still opens; the problems
are surfaced through validation rather than blocking the load.

### UI Behaviour

Loading is initiated from the toolbar **Import** menu (see [02-ui.md](02-ui.md)).
Import is a menu rather than a single button so it can host future sources without
changing the toolbar shape. On successful load the status bar shows the file name
and saved state.

### Architecture

Loading produces a `BPXDocument` from bytes via `bpx_gateway.py`, which is the only
module that imports `bpx`. The raw dictionary becomes the editable source of
truth; the object tree and validation issues are derived from it (see the Document
Lifecycle in [01-architecture.md](01-architecture.md)).

### Dependencies

- `core/bpx_gateway.py`, `core/document.py` for loading and derivation.
- The toolbar Import menu in `ui_qt/`.

### Implementation Notes

Because invalid files must open, loading must not require successful validation.
Validation runs against a copy of the raw dict and its result is stored as derived
issues, never as a gate on loading.

### Design Rationale

Import is modelled as a menu, not a single Open button, because it is the seam
through which future parameter sources (templates, databases, recent files) are
introduced. Modelling it as a hub now avoids a later toolbar redesign.

### Future Extensions

External database and library sources (for example LIIONDB) are introduced as
anti-corruption adapters mirroring `bpx_gateway.py` and surfaced under the same
Import menu. These remain in [05-future.md](05-future.md) until designed.

Under the Workspace-centred direction ([00-project.md](00-project.md)), opening a
file becomes a *Workspace* action rather than an Editor action, and a dedicated
Workspace page hosts document- and workspace-level information (title,
description, references, BPX version, model, Primary/Reference details) alongside
Recent documents and new-document actions. The Workspace page, the contextual
toolbar that hosts these actions, and contextual launch are future design in
[05-future.md](05-future.md).

---

## 2. Tree Navigation

### Overview

The tree presents the document as a navigable hierarchy of BPX objects. It is the
primary structural navigation surface and remains visible at all times.

### Capabilities

| Capability | Status |
|---|---|
| Derived object tree built from the raw BPX data | Implemented |
| Object selection drives the parameter list | Implemented |
| Validation markers on the lowest visible affected object | Implemented |
| Two-tier selection: object path and optional parameter path | Implemented |

### User Workflow

The user browses the tree, expands branches and selects an object. Selecting an
object populates the parameter list with that object's direct parameters. The tree
never collapses or filters in response to search or validation; it only reveals.

### UI Behaviour

The tree contains BPX objects only, never individual parameters. Validation
markers appear on the lowest visible object containing an issue; ancestors do not
duplicate the same marker once the branch is open. Pane responsibilities are
defined in [02-ui.md](02-ui.md).

### Architecture

The tree is derived by walking the actual raw data rather than the schema, so BPX
polymorphism (SPM/SPMe/DFN/Partial, single/blended electrodes) is expressed
naturally by the data shape. `tree_model.py` produces a UI-neutral tree of
`TreeNode` objects; `ui_qt/tree_model.py` adapts it to Qt.

### Dependencies

- `core/tree_model.py` for the UI-neutral tree.
- The two-tier selection state on `DocumentSession`.
- `NavigationService` for reveal-on-navigate.

### Implementation Notes

Tree selection updates `state.active.selected_path` and clears or updates the
parameter selection. The tree subscribes to navigation notifications and expands
ancestors of a navigation target rather than owning navigation logic.

### Design Rationale

Walking the data rather than the schema keeps the tree correct across BPX model
variants without special-casing each model type, and keeps the tree honest about
what the document actually contains.

### Future Extensions

Multi-document workspaces and comparison navigation reuse the same tree and the
same navigation service. These remain in [05-future.md](05-future.md).

---

## 3. Parameter Inspection

### Overview

Parameter inspection presents the direct parameters of the selected object and,
for a selected parameter, a detailed view including value, unit, schema
description and validation state.

### Capabilities

| Capability | Status |
|---|---|
| Parameter list for the selected object | Implemented |
| Parameter selection drives the Inspector | Implemented |
| Inspector shows value, unit and schema metadata | Implemented |
| Parameters classified by kind (scalar, integer, enum, function, table, unknown) | Implemented |
| Parameter information popover ( i ) surfacing rich BPX metadata | Planned |
| Self-contained ParameterCard (title, validity badge, summary description in the card) | Planned |

### User Workflow

The user selects an object in the tree, sees its parameters in the parameter list,
and selects a parameter. The Inspector then shows that parameter's detail and,
where the kind supports it, its editing controls.

### UI Behaviour

The parameter list shows direct parameters of the selected object only. The
Inspector is the selected parameter's work surface and the home for all
parameter-centric tools, added as tabs in the Inspector secondary workspace (see
[02-ui.md](02-ui.md)). All three editor panes stay visible during inspection.

### Architecture

Parameters are `ParameterItem` objects owned by a `TreeNode`. Classification into
`ParameterKind` is declared-type first: schema metadata is authoritative, and a
value's runtime type does not change which editor opens. The classification
rules, including the `meta=None` contract for user-defined/custom parameters
(metadata absence is a valid first-class state; value shape classifies when
metadata is genuinely absent), are defined in [01-architecture.md](01-architecture.md).

### Dependencies

- `core/parameter_types.py` for classification and kind metadata.
- `core/bpx_gateway.py` for schema metadata (units, descriptions).
- `core/tree_model.py` for parameter rows.

### Implementation Notes

Declared-type-first classification means an invalid stored value (for example a
string in a float field) is still inspected and edited as its declared kind rather
than switching to a raw/read-only view.

### Design Rationale

Making the Inspector the single parameter work surface — rather than a separate
detail page per concern — keeps editing, and later analysis and documentation,
composed over one selected parameter.

### Future Extensions

Analysis and References sections over the selected parameter are specified in
[Analysis and Visualisation](#9-analysis-and-visualisation) and
[05-future.md](05-future.md).

Rich parameter *documentation* — a parameter's physical meaning, units, accepted
types, functional dependence, model availability, measurement methods,
specification links and symbols — is delivered on demand through an information
popover anchored to the ParameterCard, triggered by an ( i ) affordance, rather
than a secondary-workspace tab. Its content is fed by a unified parameter-metadata
provider combining `FieldMeta` with a separate educational-metadata source (see
the seam in [01-architecture.md](01-architecture.md)). Delivering the popover
requires making the ParameterCard self-contained — moving the title, validity
badge and summary description into the card — while the existing editing/commit
contract is unchanged. The popover is the feature; the card refactor is the
supporting work. Both are scheduled in [04-roadmap.md](04-roadmap.md), and the
richer educational-metadata dataset itself remains future work in
[05-future.md](05-future.md).

---

## 4. Editing

### Overview

Editing changes parameter values in the raw working document. It is the
foundational capability of the application (see [00-project.md](00-project.md)) and
is designed to accept invalid work-in-progress input so that broken files can be
repaired in place.

### Capabilities

| Capability | Status |
|---|---|
| Scalar editing | Implemented |
| Integer editing | Implemented |
| Enum editing | Implemented |
| Basic function-expression editing (constant or expression string) | Implemented |
| Enter-to-commit / Escape-to-revert model | Implemented |
| Command-based mutation with undo | Implemented |
| Undo (toolbar action, and focus-aware `Ctrl+Z`) | Implemented |
| Unknown/raw fallback editor | Implemented |
| Declared-kind taxonomy (text, boolean, map, series; table narrowed to `InterpolatedTable`) | Planned |
| Mode strip on union-typed fields (verbatim BPX vocabulary, per-mode drafts, conditional Raw) | Planned |
| Text editing (auto-growing, Shift+Enter newline, pattern hint) | Planned |
| Boolean editing (toggle) | Planned |
| Per-material map editing (keys seeded from sibling Particle names) | Planned |
| Series inline grid (raw-object cells, add/remove row, no coercion) | Implemented |
| Table inline grid, expanded in-place editor, paste and CSV import | Planned |
| Remove parameter (row context menu) | Planned |
| Section add/remove controls | Planned |
| Tree editing (add/remove sections; add/rename/remove materials and experiments) | Planned |
| Enhanced function-expression editor (syntax highlighting, validation) | Planned |
| Model-switch handling for structural model changes | Planned |
| Compact quick inputs in the parameter list | Planned |

### User Workflow

The user selects a parameter, edits its value in the Inspector card for its kind,
and presses Enter to commit. The value — valid or invalid — is written to the raw
working document, and validation re-runs and updates issues. Escape reverts an
uncommitted draft.

### UI Behaviour

Editing is performed in per-kind cards in the Inspector, selected by
`ParameterKind` rather than by parameter name. The commit model is:

- **Enter commits** the current raw input to the working document, valid or
  invalid.
- Invalid data is not silently accepted by the validated BPX model; it is surfaced
  as validation issues after revalidation.
- Cards emit raw user input and never gatekeep values.
- **Escape reverts** the uncommitted draft.
- Blur does not commit.
- Detached footer Apply/Reset buttons are not used.

Any `allows_function` field may hold either a numeric constant or a
function-expression string; both are editable today.

#### Input system (Planned)

The input system is designed by declared kind — one card per kind, one
skeleton for every card (title, authoring flag, validity badge, ( i ) info
affordance; mode strip when the declared type is a union; value area; hint
line fed by `FieldMeta.examples`; description):

- **Kind is declared; mode is chosen.** The schema's declared type fixes one
  `ParameterKind`. Union-typed fields carry a **mode strip** naming each legal
  representation in verbatim `bpx` schema vocabulary — `Float` · `Function` ·
  `InterpolatedTable` for `FloatFunctionTable` fields; `FloatInt` ·
  `dict[str, FloatInt]` for per-material fields. Labels, hints and messages are
  taken from the BPX schema unchanged, never translated. The stored value's
  shape picks the initial mode; switching modes changes the representation.
  Each mode keeps its own draft until commit or Escape; commit writes only the
  active mode's value.
- **Raw mode is conditional.** When a stored value cannot be represented
  structurally (a ragged table, a non-numeric series entry), the card opens in
  a Raw mode with a notice, and the structured modes become available once the
  value parses. Values are never silently coerced or discarded.
- **Empty and null.** An empty text input commits `""`; an empty numeric input
  commits `null`. A card commits only when its draft differs from the committed
  value, so a no-op Enter never rewrites a stored `null`. Nullable fields carry
  an explicit *Set to null* action. Removing the key itself is the separate
  Remove-parameter action, keeping presence and emptiness independent.
- **Multi-line text.** Enter commits everywhere; Shift+Enter inserts a newline
  in multi-line text fields, so the app-wide commit contract is unchanged.
- **Large values.** Series and table cards show a compact inline grid plus an
  expanded editor that temporarily replaces the card within the Inspector pane
  (✕ returns; see [02-ui.md](02-ui.md)). Paste (with a preview reporting
  rejected cells) and CSV import (with column mapping for experiment data) are
  first-class. A series card in a Validation run shows its sibling columns
  read-only, so length mismatches are visible while editing; a CSV import
  there offers to fill all sibling columns from the same file.
- **Reference slot.** Every card's value row reserves a trailing slot for a
  future Reference document's value and delta; nothing renders there today.

### Architecture

Editing is command-based: `commands.py` describes intent, `editing.py` performs
pure raw-dict mutation, `command_service.py` previews and executes with structural
guardrails, and `DocumentSession` records undo and dirty state. Committing a card
runs `apply_value`, which is a `SetValue` command, so a value edit is undoable on
the same stack as adding or removing a parameter. A card's architectural contract
is fixed: it edits one `ParameterItem`, emits raw input, and does not decide
validity. See the Editing and Command architecture in
[01-architecture.md](01-architecture.md).

**Grid cards (`SeriesCard`, and later interpolated tables) hold raw objects, not
numbers.** `NumericGrid` is a `QTableView` over a small table model whose cells
are the same lenient values the line editors emit (`cards/values.py`): a typed
`oops` stays the string `"oops"`, a blank cell is `None`, and neither is ever
coerced — the validator reports the type error. The registry keeps a card
read-only only when the stored value has *no* grid representation at all (a
dict, a nested list, or a `bool`, which would round-trip as `"True"`); a
`None`-valued or `None`-celled series is representable, because the grid
produces exactly those. Enter and Escape layer without colliding: inside an open
cell editor they are Qt's cell confirm/cancel; on the grid itself they are the
app-wide commit/revert.

**Undo restores the selection too.** Each undo entry stores the document *and*
the selection that was current when the command ran, so undo navigates to the
change it reverted. Without this, undoing after navigating away would silently
alter a parameter that is not on screen — and there is no redo to recover it.

**Undo has two surfaces, deliberately unlike each other.** The toolbar's *Undo*
button is a document command, like Save and Export beside it: it reverts the last
committed change whatever holds keyboard focus, and greys out when there is
nothing to revert.

`Ctrl+Z` is *focus-aware*, because a window shortcut is matched before the focused
widget sees the key, so binding it unguarded would strip undo from every text
field in the app, the search box included. It resolves in three steps:

1. a focused text editor with typing of its own to undo — undo that typing;
2. otherwise, a focused card holding an uncommitted draft — do nothing. A spin
   box or combo box has no undo history to offer, and reverting the previous
   commit instead would change a parameter the user is not editing. Escape
   reverts the draft; the toolbar button still reverts the document;
3. otherwise — undo the document.

Committing rebuilds the card around a fresh widget with neither typing history nor
a draft, so the next `Ctrl+Z` reaches the document. There is still no redo anywhere.

### Dependencies

- `core/commands.py`, `core/command_service.py`, `core/editing.py`,
  `core/structure.py`.
- Per-document undo and dirty state on `DocumentSession`.
- The Inspector cards in `ui_qt/cards/`.
- The `meta=None` contract for user-defined parameter metadata
  ([01-architecture.md](01-architecture.md)) is resolved: authoring-created
  parameters do not synthesise or persist metadata, and absence is a valid
  classification state, so this no longer blocks or constrains section
  add/remove.

### Implementation Notes

Committing invalid input is intentional: the derived validated model rejects it
visibly rather than the card refusing it. This keeps the raw dict the source of
truth and preserves the ability to repair invalid files.

### Design Rationale

Enter-to-commit with co-located cards replaced detached footer buttons, which sat
far from the input, and replaced blocking invalid commits, which contradicted the
requirement to support invalid BPX files. Committing per keystroke or on blur were
rejected as surprising. The single emit-raw contract also serves future
function/table cards and remediation auto-fixes. The cost is that Enter-to-commit
is implicit and relies on clear affordances.

### Future Extensions

An enhanced function editor, an editable table grid, section add/remove, an
unknown/raw fallback and model-switch handling are Planned above. Broader
authoring-driven editing states are covered in [Authoring](#8-authoring).

---

## 5. Validation

### Overview

Validation continuously reports whether the raw working document satisfies
BPX/schema rules. It guides the user to problems without locking the editor, and
it keeps schema validation strictly separate from any future plausibility
checking.

### Capabilities

| Capability | Status |
|---|---|
| Continuous BPX schema validation via the `bpx` package | Implemented |
| Normalised `ValidationIssue` records (path, message, severity) | Implemented |
| Best-effort mapping from validation paths to visible objects/parameters | Implemented |
| Validation workspace listing all document issues | Implemented |
| Parameter-scoped Issues tab in the Inspector secondary workspace | Implemented |
| Keyboard navigation of issues (Enter-to-activate) in the Validation workspace and Issues tab | Planned |
| `IssueKind` classification for actionable remediation | Planned |
| Pure remediation functions (edit, move, choose model, map materials, add section) | Planned |
| Restored field paths for root-landing warnings | Planned |
| Optional warning hide/ignore for intentional modelling decisions | Planned |

### User Workflow

Validation runs automatically as the document changes. The user reviews all issues
in the Validation workspace and navigates to an affected object or parameter by
selecting an issue (arrow keys) and pressing Enter, or double-clicking it. The
editor stays spatially stable while the user surveys issues; only Enter (or a
double-click) commits navigation.

### UI Behaviour

Issues are visible in two places, with a strict division of responsibility:

- the **Validation workspace** (activity bar) lists **all** issues for the active
  document, including document-level and object-level issues;
- the **Issues tab** (in the Inspector secondary workspace) shows issues for the
  **currently selected parameter only**.

Activating an issue in the Validation workspace — by selecting it and pressing
Enter, or double-clicking — navigates to the affected location via
`NavigationService`.

#### Issues tab (parameter-scoped)

The Issues tab is strictly parameter-scoped and lives in the Inspector secondary
workspace (see [02-ui.md](02-ui.md)). Its behaviour follows the secondary
workspace's **workspace-state** model rather than being tied to an individual
parameter:

- The secondary workspace starts collapsed; its tab strip — including the Issues
  tab — is always visible so issues stay discoverable.
- The Issues tab always shows the selected parameter's current issue count as a
  badge on the tab label (for example `Issues` or `Issues (2)`), updating live
  during preview validation, whether or not the panel is open.
- Opening the tab shows that parameter's issue list. While the tab is open,
  changing the selected parameter simply refreshes the list for the new
  parameter; it does not close the workspace.
- Selecting a parameter never opens or closes the workspace. If the workspace is
  collapsed, selecting a parameter with issues updates only the Inspector
  validity badge and the Issues tab count — it does not force the panel open.
- Only the user collapses the workspace, by clicking the active tab again.

Document-level and object-level issues are never shown in the Issues tab; they
belong to the Validation workspace.

#### Keyboard navigation (Planned)

Both issue lists — the Validation workspace and the parameter-scoped Issues tab —
are keyboard-drivable. Arrow keys move the selection; Enter/Return activates the
selected issue through `NavigationService`. Selection change alone does **not**
navigate, so the user can survey issues without the editor moving; only Enter (or
a double-click) commits navigation. Focus remains in the list after activation, so
the user can arrow to the next issue and Enter again. The persistent list
selection therefore acts as the review position, with no separate review mode or
workflow state.

### Architecture

Validation runs from the raw dict via `bpx_gateway.validate` on a copy, producing
normalised `ValidationIssue` records. `tree_model.py` maps issue paths to the
nearest visible `TreeNode` and, where possible, a `ParameterItem`, using
best-effort suffix matching. Actionable remediation is a future `IssueKind` plus
pure remediation functions in `core/`. See the Validation architecture and the
warning-path gap in [01-architecture.md](01-architecture.md).

### Dependencies

- `core/bpx_gateway.py`, `core/validation.py`, `core/tree_model.py`.
- `NavigationService` for issue-to-location navigation.
- The Inspector (for the parameter-scoped Issues tab) and the activity bar (for
  the Validation workspace).

### Implementation Notes

Pydantic issue locations do not always match visible BPX paths, so mapping is
best-effort. Some warnings currently land at the document root; restoring their
field paths is Planned and tied to the architectural warning-path gap.

### Design Rationale

**Keyboard navigation over a review mode.** Reviewing issues means editing them,
and the editor must stay spatially stable while the user works. A dedicated review
mode would add workflow state (a cursor reconciled against committed document
state) and a new UI surface for marginal gain over what already exists. The
Validation workspace is already a persistent, stable list that navigates through
`NavigationService`; making it keyboard-drivable — arrow to survey, Enter to
navigate — gives step-through review with no new mode and no new state. This keeps
`NavigationService` the single navigation mechanism and matches the SearchPopup's
Up/Down/Enter contract.

**Parameter-scoped Issues tab.** A per-parameter tab in the Inspector secondary
workspace keeps full issue text for the current parameter reachable without a
separate banner, while the Validation workspace owns document- and object-wide
issues. Scoping the tab to a parameter avoids overloading it with issues that have
no parameter context. Treating the secondary workspace as workspace state — open
across parameter changes, closed only by the user — lets the user keep issues in
view while navigating, matching the persistent problems/terminal panels of
familiar editors.

### Future Extensions

Plausibility / sanity validation against known or typical cell parameter ranges is
a separate validation layer with its own reference dataset, kept independent of
schema validation. It remains in [05-future.md](05-future.md).

---

## 6. Search

### Overview

Search is navigation, not filtering. It lets the user jump to any object or
parameter by name or path without altering the document structure.

### Capabilities

| Capability | Status |
|---|---|
| SearchPopup navigation over objects and parameters | Implemented |
| Focus by `Ctrl+F` and `Ctrl+P`, selecting existing text | Implemented |
| Keyboard navigation (Up/Down, Enter, staged Escape) | Implemented |
| Result activation through `NavigationService` | Implemented |

### User Workflow

The user focuses search (`Ctrl+F` or `Ctrl+P`), types part of an object or
parameter name, and picks a result. Activation navigates to that location through
the shared navigation service, revealing it in the tree, parameter list and
Inspector.

### UI Behaviour

The search box lives in the toolbar and is focused by both `Ctrl+F` and `Ctrl+P`;
focusing selects existing text so it can be replaced immediately. Results appear in
a custom **SearchPopup**, not a generic `QCompleter`. The popup:

- indexes both navigable objects and parameters;
- displays each result as a name over its full path;
- scrolls after approximately eight visible results;
- supports Up/Down, Enter and Escape;
- navigates the highlighted result via `NavigationService` on Enter;
- stages Escape: close popup, then clear search, then return focus to the editor.

Search never hides tree nodes or parameter rows.

### Architecture

Search consumes the same object/parameter index used for navigation and activates
results exclusively through `NavigationService` (see
[01-architecture.md](01-architecture.md) and the navigation model in
[02-ui.md](02-ui.md)). It owns no navigation logic of its own.

### Dependencies

- `NavigationService` for all result activation.
- The tree/parameter index for results.
- The toolbar search box and the SearchPopup widget in `ui_qt/`.

### Implementation Notes

The first implementation is deliberately simple: no ranking, icons, recent
searches or grouping until there is a concrete need. Mixed object/parameter results
should carry a clear type marker.

### Design Rationale

Search became navigation rather than autocomplete, so a flat-string `QCompleter`
fought the interaction design. A custom SearchPopup gives one owned navigation
surface that reaches objects as well as parameters and avoids a later
rip-and-replace. The cost is more initial work than reusing a completer.

### Future Extensions

Ranking, icons, recent searches, and searching validation, comparison or database
results through the same surface remain in [05-future.md](05-future.md).

---

## 7. Save and Export

### Overview

Save and Export are distinct operations over the raw working document. Save
persists to the current file; Export writes a copy. Keeping them distinct is what
makes the Modified/Saved state meaningful.

### Capabilities

| Capability | Status |
|---|---|
| Export / round-trip to JSON or YAML | Implemented |
| Dirty / backing-file state on `DocumentSession` | Implemented |
| Distinct Save (write back, clear Modified) vs Export (write copy, no state change) | Implemented |

### User Workflow

The user edits a document, then either **Saves** — writing changes back to the
current backing file and clearing the Modified indicator — or **Exports** — writing
a copy to a chosen path and format without changing the Modified state.

### UI Behaviour

Save and Export are separate toolbar actions (see [02-ui.md](02-ui.md)). Save
writes back to the current backing file and clears Modified; Export writes a copy
to a chosen path/format and does not change Modified. The status bar reflects the
resulting saved/modified state.

### Architecture

Both operations serialise the raw working document via `export.py`, which may still
contain invalid work-in-progress data. `DocumentSession` owns the dirty flag and
backing-file path that distinguish the two operations.

### Dependencies

- `core/export.py` for serialisation.
- Dirty and backing-file state on `DocumentSession`.
- The toolbar Save and Export actions.

### Implementation Notes

Export deliberately serialises whatever is in the raw dict, including invalid
data, so a broken file can be exported for sharing or later repair.

### Design Rationale

Save and Export are genuinely different operations; conflating them makes the
Modified/Saved indicator meaningless. Distinguishing them requires backing-file and
dirty state in `DocumentSession`, which is the accepted cost. Export is also the
seam that later generalises to simulator hand-off writers.

### Future Extensions

Simulator hand-off targets (for example PyBOP, PyProBE) and target-specific writers
behind the export layer, plus simulator compatibility checks, remain in
[05-future.md](05-future.md).

---

## 8. Authoring

### Overview

Authoring covers the lifecycle of creating, completing and maintaining BPX
documents. It is broader than editing individual values: it owns the distinction
between Complete BPX, Incomplete BPX, Skeletons and Templates, and it keeps
completion state separate from validation state.

Authoring is an accepted **core product capability and a major implementation
priority**, designed alongside editing rather than deferred (see
[00-project.md](00-project.md)). The whole feature is currently Planned, but it is
architecturally co-equal with editing.

### Concepts

- **Complete BPX** — ready for simulation or downstream use.
- **Incomplete BPX** — a genuine work-in-progress.
- **Skeleton** — a model-specific structural starting point with no invented
  scientific values.
- **Template** — a reusable skeleton or partially completed document containing
  trusted defaults for a lab, organisation, chemistry or workflow.

### Capabilities

| Capability | Status |
|---|---|
| Raw-dict model that represents invalid and partially edited documents | Implemented |
| Incomplete structural scaffolds without invented values (`document_factory.py`) | Implemented |
| Continuous validation that tolerates work-in-progress editing | Implemented |
| Add a freeform custom parameter to a section (no synthesised metadata) | Implemented |
| Add a known BPX parameter via search (section-expected + full-schema fallback) | Implemented |
| New BPX from built-in model skeletons (SPM, SPMe, DFN, Partial) | Planned |
| Completion status distinct from validation status | Planned |
| Completion view for unfinished required authoring work | Planned |
| Expected-but-missing parameter rows in the editing workflow | Planned |
| Upload/open skeleton workflows | Planned |
| Save as Template and New from Template workflows | Planned |

### User Workflow

The user starts a new document from a model skeleton (or a template), then works
through the completion view to fill required authoring work. Expected-but-missing
parameters appear in the editing workflow so the user can supply real values.
Completion tracks what remains to finish the document, separately from whether the
current data is valid. The user may save a document as a template for reuse.

### UI Behaviour

Validation remains the surface for schema errors and warnings; completion is a
distinct authoring concept for unfinished work and must not be shown as validation
failure. Completion navigation reuses the shared navigation model (see
[02-ui.md](02-ui.md)) so the user moves from an authoring task into the normal Tree
→ Parameter list → Inspector workflow. Expected-but-missing parameters are surfaced
as editable rows that write real BPX values only when committed.

Parameters are added from a section-scoped "+ Add parameter" header on the
parameter-list pane (see [02-ui.md](02-ui.md)). The popup lists the section's
expected BPX aliases and, on search, also surfaces other schema aliases (greyed) and
a "Create custom parameter" fallback. Every add writes an empty value through the
`AddParameter` command and reveals the new row via `NavigationService`; the validator
judges legality and nothing is fabricated.

### Architecture

Authoring builds on the completion/authoring model in the domain layer
([01-architecture.md](01-architecture.md)): the raw dict is the simulator-facing
data source, and authoring/completion state (draft, template inheritance, review
status) lives in a separate layer that never forces values into exported BPX.
`document_factory.py` creates incomplete structures without scientific defaults.
Authoring-created custom parameters do **not** synthesise or persist a
`FieldMeta`: absence (`meta=None`) is a valid first-class state under the
accepted decision in [01-architecture.md](01-architecture.md). `classify`
stays metadata-authoritative wherever metadata exists and falls back to
value-shape classification where it is genuinely absent; the BPX validator is
the source of truth for whether such a parameter is legal.

### Dependencies

- `core/document_factory.py` for skeletons.
- The completion/authoring layer (Planned) separate from exported BPX.
- The `meta=None` contract for user-defined parameter metadata
  ([01-architecture.md](01-architecture.md)), resolved: no persistence
  mechanism is needed for authoring-created parameters to be classified
  reliably.
- `NavigationService` for completion-task navigation.

### Implementation Notes

The export guarantee is absolute: internal authoring, completion or draft state
must never force fake scientific values into simulator-facing BPX output. Skeletons
provide structure only; committing a real value is what writes BPX data.

### Design Rationale

A work-in-progress BPX document is not the same product state as an incorrect one.
Collapsing missing or unconfirmed authoring work into generic validation failure
would mislead the user, and inventing scientific values to make a document look
complete would corrupt exported data. Treating authoring as a first-class lifecycle
— Complete / Incomplete / Skeleton / Template, with completion distinct from
validation — establishes a coherent long-term product model and a foundation for
guided completion. The cost is a second document-status concept alongside
validation, which requires careful UI language so users understand the difference
between incomplete and invalid. The alternatives — treating all incomplete
documents as invalid, encoding placeholders in exported BPX, or merging completion
into validation — were rejected as dishonest or confusing.

### Future Extensions

Organisation/lab/chemistry/workflow-specific templates, session change awareness,
modified indicators, a dedicated Changes review workspace, parameter authoring
states beyond present/missing, provenance and confidence tracking, review workflows
for template-derived values, and reusable parameter packs are all more speculative
and remain in [05-future.md](05-future.md) until designed and accepted.

---

## 9. Analysis and Visualisation

### Overview

Analysis and visualisation present a selected parameter graphically — for example
plotting a function or an interpolated table. It is a parameter-centric tool hosted
in the Inspector, not a separate workspace.

> **Specification status.** This feature is intentionally underspecified. The
> accepted design is limited to the placement decision (an Analysis tab in the
> Inspector secondary workspace acting as a launcher) and the initial subject
> (function and table visualisation). Detailed behaviour awaits a dedicated design
> pass and must not be invented before then.

### Capabilities

| Capability | Status |
|---|---|
| Analysis as a tab in the Inspector secondary workspace | Planned |
| Launcher model: per-tool `Show` actions that open floating visualisations | Planned |
| Function and interpolated-table visualisation (for example OCP plots) | Planned |

### User Workflow

With a parameter selected, the user opens the Analysis tab in the Inspector
secondary workspace. Rather than embedding a large graph, the tab lists the
visualisations available for that parameter — for example `OCP Curve`,
`Diffusivity`, `Conductivity`, `Statistics` — each with a `Show` action. Selecting
one opens (or toggles) a floating graph/dialog, keeping the Inspector compact.

### UI Behaviour

Analysis is a tab in the Inspector secondary workspace over the selected
`ParameterItem`, consistent with the secondary-workspace model in
[02-ui.md](02-ui.md). It is never an activity-bar workspace. The tab itself stays
compact: it is a **launcher** of per-tool `Show` actions that open or toggle
floating visualisation dialogs, not a host for large embedded graphs.

### Architecture

Analysis consumes the selected `ParameterItem` and uses BPX functions exposed
through `bpx_gateway.py` (`to_python_function()`) to evaluate expressions and
tables. It attaches at the Inspector secondary-workspace tab seam described in
[01-architecture.md](01-architecture.md); no analyzer registry is built before
concrete analyzers exist.

### Dependencies

- The Inspector secondary-workspace tab mechanism.
- `core/bpx_gateway.py` for evaluating BPX functions and tables.
- The selected `ParameterItem`.

### Implementation Notes

An analyzer registry is deliberately not built ahead of the first concrete
analyzer. The first analyzers should be implemented directly against the Inspector
secondary-workspace tab seam, each contributing a `Show` action that opens a
floating visualisation.

### Design Rationale

Analysis is a parameter-centric tool, so it belongs in the Inspector next to the
parameter, not in the activity bar and not inside editing cards. The launcher model
keeps the tab compact — the Inspector never has to surrender vertical space to a
large embedded graph — while still giving access to rich visualisations through
floating dialogs. Defining an analyzer registry before analyzers exist is
premature. The cost is that floating dialogs need their own lifecycle and
positioning conventions, defined when the first analyzer is designed.

### Future Extensions

Parameter-centric plausibility displays, docking or maximising floating
visualisations, and comparison overlays for related files or known cells remain in
[05-future.md](05-future.md).
