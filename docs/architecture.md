# Explore_BPX — Design & Architecture

The one reference for how Explore_BPX is designed: what it is for, how the
code is layered, the domain and state model, and the UI shell every feature
lives in. It is kept in sync with the code, not a spec — where this document
and the running app disagree, the app is correct. Ideas that are not yet
accepted design live in [future.md](future.md).

## Purpose

Explore_BPX exists for four activities, all first-class: **explore**,
**edit**, **validate** and **author** BPX documents. It is a desktop app
built on the official [`bpx`](https://github.com/FaradayInstitution/BPX)
package and implements none of the BPX specification itself.

## Principles

- **The raw document is the source of truth.** The editable state is the raw
  BPX dictionary, so invalid and partially edited documents remain fully
  representable. The parsed model, the object tree and all validation issues
  are derived from it.
- **Validation belongs to `bpx`.** Explore_BPX owns presentation only.
  Validation semantics and messages come from the official package and are
  surfaced faithfully, never modified or "corrected" — reproducing the
  validator's exact behaviour is a feature, because the app's job is to show
  users what the validator thinks of their file.
- **Completion is distinct from validation.** Validation answers whether the
  data satisfies BPX rules; completion answers whether a document is finished
  for an authoring workflow. A work-in-progress document is not the same
  thing as an incorrect one.
- **Never invent scientific values.** The app never writes placeholder values
  to make a document look complete or valid; exported BPX contains only data
  the user is prepared to claim.
- **The unit of work is a Workspace** — one Primary document and optionally
  one read-only Reference. How many documents are present is data, not an
  application mode, so comparison is a capability of the editor rather than a
  separate mode, and multi-document support is additive.

## Scope

In scope: open JSON/YAML BPX files, including invalid or incomplete ones;
navigate a derived object tree and per-object parameter list; inspect schema
metadata (units, descriptions); validate continuously; edit every parameter
kind; author new documents from model skeletons with completion guidance;
dock reference documents for comparison; save and export as JSON or YAML.

Non-goals:

- **Reimplementing BPX** — schema, parsing and validation stay with `bpx`.
- **Plausibility checks in the gateway** — sanity checks against reference
  data are a separate future concern and must never contaminate the BPX
  integration layer.
- **Disabled placeholder UI** — controls appear when their workflow exists,
  never as greyed-out promises.
- **Speculative abstractions** — the architecture keeps stable extension
  seams rather than frameworks built ahead of need.

## Layers

Dependencies point one way only:

```text
ui_qt  →  state  →  core  →  bpx
```

| Layer | Responsibility |
|---|---|
| `app/ui_qt/` | PySide6 frontend: renders state, collects input, coordinates navigation. |
| `app/state/` | Frontend-agnostic session state: active document, selection, undo, dirty/backing-file state. |
| `app/core/` | BPX integration, document model, validation, editing primitives, commands, structural queries. |
| `bpx` | The official BPX package, pinned as a dependency. |

`core/` and `state/` never import a UI framework;
[tests/test_boundaries.py](../tests/test_boundaries.py) enforces this. All
coupling to `bpx` lives in one module, `core/bpx_gateway.py`, through public
APIs only. The pin is exact (`bpx==1.1.1`), and the UI is driven by the
schema metadata `bpx` publishes, so new fields in future BPX versions appear
without app changes.

## State model

`DocumentSession` owns everything per-document: the current document, the
selected object and parameter paths, undo history, and dirty state with its
backing file. `AppState` owns app-global state and exposes one active session
as `state.active`. A read-only reference document is held beside it as a
disposable `ReferenceSnapshot` — no session, no undo — docked from a file or
from the bundled reference library.

## Domain model

**Raw dict.** A parsed Pydantic `BPX` object cannot represent invalid or
partial data, so the raw dictionary is the editable state. Validation runs
`bpx.parse_bpx_obj` on a **deep copy** (it mutates its input) and normalises
errors and warnings into `ValidationIssue` objects. Pydantic locations do not
always match visible BPX paths, so `core/tree_model.py` suffix-matches each
issue onto the nearest visible node and, where possible, its parameter.

**Tree and parameters.** `BPXDocument` holds the raw dict plus the derived
tree and issues. The tree separates navigable BPX objects (`TreeNode`) from
editable values (`ParameterItem`) and is built by walking the actual data,
which handles BPX polymorphism (SPM/SPMe/DFN/Partial models, blended
electrodes) naturally — the shape is in the data.

**Parameter kinds.** Parameters are classified into kinds (scalar, integer,
text, boolean, enum, function, map, series, table, section, unknown),
**declared-type first**: when the schema knows the field, the declared type
alone fixes the kind, and an invalid stored value (say, a string in a float
field) never changes which editor opens. A union-typed field is one kind
whose card offers a mode per legal representation, in the schema's own
vocabulary; the stored shape only picks the initial mode. Value shape
classifies only where the schema is silent: custom parameters and undeclared
structures.

**Custom parameters.** A user-authored parameter is an ordinary raw-dict
entry whose schema metadata is simply absent — nothing is synthesised or
persisted for it, and the `bpx` validator remains the sole judge of whether
it is legal.

**Completion.** Completion is a pure, stateless projection over the committed
raw dict and schema (`core/completion.py`) — recomputed on every refresh,
never persisted. It cannot be derived by filtering validator output, because
`bpx`'s `mode="before"` validators short-circuit: one section-level problem
can suppress that section's own required-field errors, and an absent section
collapses to a single diagnostic that never names its required leaves.
Completion reads the schema directly, so it can list what validation in those
states cannot — while never judging legality itself.

## Editing and undo

Every mutation travels one spine: `core/commands.py` describes intent,
`core/editing.py` performs pure raw-dict mutations, `core/command_service.py`
previews and executes with structural guardrails, and `DocumentSession`
records history. Value edits included — committing a card executes a
`SetValue` command, undoable exactly like a structural change.

An undo entry is a `(document, selected object, selected parameter)` triple:
selection is part of what a command changes, so undo restores it and lands on
the change it reverted. Invalid input may be committed — it surfaces as
validation issues rather than a blocked commit, which is what keeps broken
files openable and repairable.

## Navigation

`NavigationService` (`ui_qt/navigation.py`) is the single owner of
navigation: it resolves a target path, updates the selected paths in state,
and emits one notification. Each view then reveals its own part of the target
— the tree expands and selects, the parameter list selects, the Inspector and
context bar update, and the destination scrolls into view with a temporary
highlight. Features (search, diagnostics, reference links) request navigation
by path and never drive widgets directly.

## Module map

| Module | Responsibility |
|---|---|
| `core/bpx_gateway.py` | The **only** module importing `bpx`: load JSON/YAML, validate, build schema metadata. |
| `core/document.py` | `BPXDocument`: raw dict plus derived tree and validation issues. |
| `core/editing.py` | Pure raw-dict mutation primitives. |
| `core/commands.py` / `command_service.py` | Command intent; preview/execute with guardrails. |
| `core/structure.py` | Frontend-agnostic structural and capability queries. |
| `core/completion.py` | Stateless completion projection. |
| `core/tree_model.py` | UI-neutral object tree, parameter rows, issue-path matching. |
| `core/parameter_types.py` | Parameter-kind classification and metadata. |
| `core/example_library.py` / `reference_library.py` | Bundled data sources behind gateway-style adapters. |
| `state/document_session.py` / `app_state.py` | Per-document session; app-global state. |
| `ui_qt/main_window.py` | Shell assembly and top-level wiring. |
| `ui_qt/navigation.py` | `NavigationService`. |

## UI shell

A fixed, editor-style shell with familiar IDE conventions — not a wizard or
dashboard. The structure stays visible at all times; search and validation
navigate to locations rather than filtering or replacing the hierarchy.

```text
[top context bar spans the main content area]
[activity bar] | Tree | Parameter list | Inspector
[bottom status bar]
```

- **Activity bar** — a VS Code-style icon rail switching the content area
  between top-level pages: **Workspace** (open or create documents, document
  info, and the reference card for docking a reference from a file or the
  bundled library), **Editor** (the three-pane view below) and
  **Diagnostics**. It is reserved for major pages; parameter-centric tools go
  in the Inspector instead. The Diagnostics badge counts issues — red for
  errors, amber for warnings only, and no badge for a merely unfinished
  document: **red means wrong, never unstarted**.
- **Top context bar** — the document's identity (`Title · BPX vX.Y`); a
  context surface, not a clickable breadcrumb.
- **Tree** — BPX objects only, never values. Validation markers sit on the
  lowest visible object containing an issue. Structure is edited here through
  a right-click menu that offers only the schema's real degrees of freedom:
  add expected sections, add or rename user-named materials, experiments and
  User-defined subsections, and remove anything structurally removable
  (removing populated content asks first; either way it is one undo step).
- **Parameter list** — the direct parameters of the selected object, each row
  with a read-only value preview; a `null` value renders muted, and a
  severity dot mirrors the Diagnostics page. **+ Add parameter** creates
  (typed: scalar, text, boolean, table or series); actions on an existing row
  (rename, duplicate, move, remove) live in its context menu. A collapsed
  `▸ N fields to add` line lists schema-expected fields still absent.
- **Inspector** — the selected parameter's work surface: the editing card for
  its kind on top (tables plot a live chart preview beside the grid), and
  below it a collapsible tabbed secondary workspace (**Issues**,
  **Documentation**; future tools add tabs here, not new pages). Large grids
  expand in place within the pane; floating windows are reserved for
  read-only visualisation, such as the validation-run comparison charts. A
  card's ( i ) opens a quick documentation popover; the Documentation tab
  carries the full prose.
- **Diagnostics page** — a summary strip over a section rail beside a detail
  pane of per-section **Issues** and **Outstanding** groups. The strip's
  chips double as view-only filters that never change any reported count.
  `core/page_buckets.py` supplies the one grouping that the strip, rail and
  pane all render from, so they cannot disagree.
- **Toolbar and status bar** — Save, Export (JSON/YAML), Undo, Redo and
  Search sit on the right of the top bar; opening files lives on the
  Workspace page. The status bar carries source and modified/saved state.

## Interaction conventions

- All navigation goes through `NavigationService`; search and validation
  navigate, they never filter or hide the structure.
- Guidance informs, it does not lock: invalid edits may be committed.
- Creation is offered by visible affordances; actions on an existing row or
  node live in its context menu.
- Enter commits the active card; Escape reverts its draft. In popups Escape
  is staged: it clears typed text first, then closes.
- `Ctrl+F` / `Ctrl+P` focus search. `Ctrl+Z` is focus-aware (a text field's
  own undo first, the document otherwise); the toolbar Undo/Redo always act
  on the document.
- Transient popups dismiss uniformly: one click outside closes the popup and
  is consumed, so a second click acts.

## Constraints

Enforceable rules that hold at all times:

- `core/` and `state/` stay Qt-free (`tests/test_boundaries.py`).
- The raw dict stays the editable source of truth.
- Completion stays a stateless projection; no authoring state may push
  placeholders into exported BPX data.
- BPX schema and validation semantics stay delegated to `bpx`; plausibility
  checks never enter `bpx_gateway.py`.
- New features attach through the existing seams rather than duplicating
  traversal or validation logic: the command spine for editing and creation,
  Inspector tabs for parameter-centric tools, gateway-style source adapters
  for external data (`core/example_library.py` and
  `core/reference_library.py` are the shipped examples — the bundled
  PyBaMM-derived sets are generated offline by
  `scripts/generate_reference_library.py`, so the app itself never imports
  PyBaMM), and `core/export.py` for simulator hand-off.
