# Explore_BPX — Architecture

Layered structure, domain model, state model and the constraints that must
hold. Product principles live in [00-project.md](00-project.md); UI structure in
[02-ui.md](02-ui.md). Rationale is inline with the decision it explains. This is
reference, not a spec — the code is authoritative where they differ.

## Layered Architecture

Dependencies flow in one direction only: `ui_qt` → `state` → `core` → `bpx`.
`tests/test_boundaries.py` enforces this; a change that needs to break it should
move code inward instead.

| Layer | Responsibility |
|---|---|
| `ui_qt/` | PySide6 frontend. Renders state, collects input, coordinates UI navigation. |
| `state/` | Frontend-agnostic session state: active document, selection, undo, dirty/backing-file state. |
| `core/` | BPX integration, validation, document model, tree generation, editing primitives, commands, structural queries. |
| `bpx` | Official BPX package, pinned as a dependency. |

`core/` and `state/` must never import a UI framework.

## State Model

`DocumentSession` owns per-document state: the current `BPXDocument`, the
selected object path, the selected parameter path, undo history, and dirty state
with its backing-file path. `AppState` owns app-global state and exposes a single
active `DocumentSession` via `state.active`.

**Rationale.** Undo, selection and dirty state are inherently per-document, so
they belong to a session. Conceptually the application edits a **Workspace** —
one Primary document and optionally one Reference document (see
[00-project.md](00-project.md)); today's single active `DocumentSession` is the
degenerate one-document Workspace. Exposing exactly one `active` session keeps
the current app simple while making multi-document support purely additive: a
future `Workspace` can hold a Primary and an optional Reference session while UI
code continues to interact with `state.active.*` unchanged. Introducing a
`Workspace` container before any consumer needs it would be exactly the
speculative abstraction this architecture rejects.

## Domain Model

### Raw dict as source of truth

A parsed Pydantic `BPX` object cannot represent invalid or partially edited data,
so Explore_BPX stores the **raw dictionary** as the editable source of truth. The
parsed BPX model and validation issues are derived by calling `bpx.parse_bpx_obj`
on a **deep copy** — `parse_bpx_obj` mutates the object it receives, so validation
must run against a copy and never mutate the raw working document.

### Completion and authoring model

Completion is derived separately from BPX validation, in line with the accepted
principle that the two are distinct (see [00-project.md](00-project.md)).
Validation, delegated to `bpx`, answers whether the current data satisfies
BPX/schema rules. Completion answers whether the document is finished for an
authoring workflow.

Completion is **not** a persisted layer — it is a **pure, stateless projection
over `(raw, model)`**, implemented in `core/completion.py` and shaped like
`structure.py`'s own capability queries. It holds nothing between calls and is
recomputed fresh from the committed raw dict on every refresh; drafts never feed
it. `completion_for(path, value, model)` returns a section's Expected fields;
`document_completion(raw)` aggregates the document's Required-only outstanding
tasks; `partition_issues` is the one function that reads validator diagnostics,
and only to decide which are already accounted for by a task (never to silence
them). Completion never judges legality: the `bpx` validator remains the sole
authority on valid/invalid, at every altitude.

Completion cannot be derived by filtering validation diagnostics, which is why it
is a separate query: `bpx`'s `mode="before"` validators short-circuit sibling
checks (a section-level one can suppress that section's own required-field errors;
the root validator suppresses `State`/`Validation` diagnostics entirely — including
the root demand for `State` — whenever `Parameterisation` has any problem), and an
absent section or an unrecognised model collapses to one diagnostic with its
required leaves never enumerated. Completion instead reads the schema and raw dict
directly, so it can name what validation, in these suppressed states, cannot.

Missing scientific values must never be represented by fake BPX values solely to
satisfy the editor: a completion task may say a field is missing, but only
committing a real value writes BPX data. Any future authoring state that needs to
persist — drafts, template inheritance, review status, provenance — is a distinct,
not-yet-built concept, and must likewise never be conflated with exported BPX data.

### Document, TreeNode and ParameterItem

`BPXDocument` contains the raw working dictionary, the derived validation issues,
and the derived object tree. The tree separates navigable BPX objects from
editable values:

```text
TreeNode      = navigable BPX object
ParameterItem = direct parameter owned by a TreeNode
```

Tree nodes are produced by walking the actual raw data rather than only the
schema, which handles BPX polymorphism naturally: SPM/SPMe/DFN/Partial and
single/blended electrode structures are already expressed in the data shape.

Parameters are classified into `ParameterKind` values (scalar, integer, text,
boolean, enum, function, map, series, table, section, unknown), **declared-type
first, universally**: when schema metadata is available the declared field type
alone fixes the kind, and the stored value's runtime type never changes which
editor opens — an invalid stored value (e.g. a string in a float field) never
flips the kind.

Union-typed fields (`FloatFunctionTable`, `FloatInt | dict[str, FloatInt]`) are
one kind, not several: the kind identifies the declared union, and the card for
that kind carries a **mode strip** naming each legal representation in verbatim
`bpx` schema vocabulary. The stored value's shape selects the *initial mode* only;
the user may switch mode freely.

Value shape still classifies in exactly two places: metadata-absent parameters
(below), and undeclared dicts/lists whose topology no schema field describes. A
field the schema declares as a value is always a `ParameterItem`, never a
`TreeNode`, whatever it currently holds.

### User-defined parameter metadata

A user-authored custom parameter is an ordinary raw-dict entry
(`section[alias] = value`) whose BPX metadata is simply **absent** (`FieldMeta`
is `None`). Nothing is synthesised and nothing is persisted for it. When metadata
exists it dominates classification; when it is genuinely absent, value shape is
the honest classifier, and absence is a valid first-class state, not a gap to be
closed.

`classify` implements this: metadata-authoritative when `meta` is known, falling
back to value-shape classification when `meta` is `None`. The BPX validator is the
source of truth for whether a custom parameter is legal — the app must not
fabricate metadata to make one look schema-known.

## Core modules — where things live

The load-bearing modules that define the architecture. Other `core/` modules are
descriptive-data or serialisation helpers and are self-describing.

| Module | Responsibility |
|---|---|
| `bpx_gateway.py` | The **only** module that imports `bpx`. Loads JSON/YAML, validates, builds parameter metadata from the schema. |
| `document.py` | `BPXDocument`: raw dict plus derived tree and validation issues. |
| `editing.py` | Pure raw-dict mutation primitives. |
| `commands.py` / `command_service.py` | Command intent, and preview/execute orchestration over mutation primitives with structural guardrails. |
| `structure.py` | Frontend-agnostic structural and capability queries. |
| `completion.py` | Stateless completion projection over `(raw, model)`. |
| `tree_model.py` | UI-neutral object tree, parameter rows, validation-path matching. |
| `parameter_types.py` | Value classification and parameter-kind metadata. |

## BPX Integration Strategy

Explore_BPX consumes `bpx` as a pinned PyPI dependency (`bpx==1.1.1`), coupling
isolated in `core/bpx_gateway.py` via public APIs only (`parse_bpx_obj`, `BPX`,
`model_json_schema()`). A local editable checkout (drifts), a Git dependency
(heavier) and a vendored schema (duplicates the logic we delegate) were rejected.

## Navigation Architecture

`NavigationService`, in `ui_qt/`, is the single owner of navigation: it resolves a
target path, updates `state.active.selected_path` / `selected_parameter_path`, and
emits one notification. Views subscribe and reveal their own part of the target
(tree, parameter list, Inspector, context bar) — see [02-ui.md](02-ui.md).
`state/` only stores the selected paths; navigation logic is frontend
orchestration and does not belong in `state/`.

**Rationale.** A single owner prevents duplicated, competing navigation logic
while keeping panels plug-in subscribers to one notification rather than driven
imperatively. Every current and future consumer (search, validation review,
comparison, documentation links, analysis) navigates through this one service.

## Validation Architecture

Validation runs from the raw working dict via `bpx_gateway.validate`, using a
copy. Errors and warnings are normalised into `ValidationIssue` objects keyed by
alias paths. Pydantic locations are not always identical to visible BPX paths
(they may be relative to a section, or carry union type tags such as
`float`/`int`), so `tree_model.py` performs best-effort suffix matching to map
issues to the nearest visible `TreeNode` and, where possible, a `ParameterItem`.

## Editing Architecture

Editing is built around command intent and raw-dict mutation: `commands.py`
describes operation intent, `editing.py` performs pure raw-dict mutations,
`command_service.py` previews/executes with structural guardrails, and
`DocumentSession` records undo history and dirty/backing-file state.

Every mutation travels this spine, value edits included:
`DocumentSession.apply_value` is a thin wrapper over `execute_command(SetValue(...))`
rather than a second, history-less mutation path — committing a card is undoable
exactly as adding or removing a parameter is.

An undo entry is a `(document, selected_path, selected_parameter_path)` triple,
not a bare document: selection is part of the state a command changes, so undo
restores both and lands on the change it reverted. Because the selection was valid
in the document it is stored beside, it is always valid again once that document
is restored.

The raw dict remains the editing state: user input can be committed even when
invalid, and the derived validated model surfaces that as validation issues rather
than blocking the commit — preserving the ability to open, edit and repair invalid
BPX files. A card edits one `ParameterItem`, emits raw input, and does not decide
whether the value is valid; validation is a derived concern.

## Extension seams

The architecture defines stable places where planned and future capabilities
attach, **without building the capabilities themselves ahead of need**. The
principle: new features connect through existing state, command and navigation
seams rather than duplicating traversal or validation logic. The main seams are
the command spine (`command_service.py`, `editing.py`, `document_factory.py`) for
editing and creation; the Inspector secondary-workspace tab strip for
parameter-centric tools (Issues, Documentation, future Analysis/References); an
anti-corruption adapter mirroring `bpx_gateway.py` for external data sources
(`example_library.py` is the first, real one; `reference_library.py` is the
second — whole-document PyBaMM-derived reference sets, generated offline by
`scripts/generate_reference_library.py`, consumed via
`ReferenceSnapshot.from_library` / `AppState.open_reference_set` and the
Workspace page's Reference library dialog); `export.py` for simulator hand-off
writers; and a future `Workspace` object for multi-document comparison. Speculative
seams and their status live in [05-future.md](05-future.md).

## Architectural Constraints

These constraints are enforceable and must hold at all times:

- `core/` and `state/` must remain Qt-free (`tests/test_boundaries.py`).
- The raw dict remains the editable source of truth.
- Completion is a stateless projection recomputed from the committed raw dict; it
  and any future authoring state must not force placeholders or draft intent into
  exported BPX data.
- BPX schema and validation semantics stay delegated to `bpx`.
- Domain plausibility checks must be separate from schema validation and must
  never be added to `bpx_gateway.py`.
- Future UI features connect through existing state, command and navigation seams
  rather than duplicating traversal or validation logic.
