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
- **The unit of work is a workspace** — one editable main document plus up to
  four read-only references (`MAX_PINNED_REFERENCES`). How many documents are
  present is data, not an application mode, so comparison is a capability of
  the editor rather than a separate mode.
- **A workspace is a live identity, not a snapshot.** "New workspace" mints
  one instantly and empty; opening a file starts one too, and adding a
  reference or swapping the main rewrites it in place. There is no save step,
  nothing that can be "changed since saved", and nothing to go stale.
  Identity is an internal id, not the main's path, so it survives a main swap
  and two workspaces may point at one file — and a workspace can exist,
  be seen and be named before it holds any document at all.
- **Nothing is discarded by a click.** Switching away shelves a workspace
  under Recent (capped, newest first). *Naming* is the promotion that stops
  one decaying — and the act that says "stop rewriting this", so an ordinary
  open beside a named workspace starts a fresh untitled one rather than
  overwriting it.

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
as `state.active`. Read-only reference documents are held beside it as
disposable `ReferenceSnapshot`s — no session, no undo — pinned from a file or
from the bundled reference library, up to `MAX_PINNED_REFERENCES`.

`state/workspace_history.py` makes that arrangement durable. It is the only
module that writes the store (one JSON file per OS user, atomic, immediate)
and it holds **pointers only** — paths, ids and open modes, never file
content and never validation results, so nothing stale can ever be presented
as a current verdict. Every restore re-reads and re-validates.

Workspaces live in one of two lists: `recent_workspaces` (untitled, newest
first, capped) and `workspaces` (named, never decaying); `current_id` names
the one on the board, which is what launch reopens. `AppState` records
against it at the open/pin funnel rather than in the UI layer, so every path
that changes the workspace is recorded without remembering to — see
`_note_main_opened`, which is where "an ordinary open never rewrites a named
workspace" lives. Its one exception: filling a named workspace's *empty*
Main slot updates in place, because there is no recorded main to guard.

**Creation is instant; persistence is deferred.** `WorkspaceRecord.main` is
optional (schema v3; a v2 store reads through the same path, since a v2
record always has a main), so a workspace exists from the moment it is asked
for. What reaches disk is filtered: a record is written only if it has a
name, a main, or references, and if the current record was filtered out the
store writes `current_id: null`. So an untouched empty board is real while
the app runs and leaves nothing behind on the next launch, while repeated
"New workspace" clicks collapse to one row through the existing
content-key dedup. A workspace with no recorded main is **empty, not
missing**: no strike, no "Not found" chip, no banner entry — nothing
recorded is nothing lost.

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
| `core/compare.py` / `source_rows.py` | The one comparison engine: row states, and the raw-JSON row model the Source page paints. No surface recomputes either. |
| `core/page_buckets.py` | The one grouping the Diagnostics strip and stream both render from. |
| `state/document_session.py` / `app_state.py` | Per-document session; app-global state. |
| `state/workspace_history.py` | The persistent workspace store: pointers only, one JSON file per user. |
| `ui_qt/workspace_panel.py` | The Workspace page: the workspaces rail and the board of files. |
| `ui_qt/source_page.py` | The Source page: two aligned raw-JSON panes and the pull gutter. |
| `ui_qt/reference_identity.py` | One badge per pinned reference, shared by every surface that names one. |
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
  between four top-level pages: **Workspace** (the rail of workspaces beside
  the board of files the current one holds, over the main document's own
  record), **Editor** (the three-pane view below), **Source** (the raw JSON)
  and **Diagnostics**. The rail is reserved for major pages; parameter-centric
  tools go in the Inspector instead. The Diagnostics badge counts issues — red
  for errors, amber for warnings only, and no badge for a merely unfinished
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
  List-valued tooltips summarise ("series · 12 values"), never dump JSON.
- **Validation runs** — one editor (`ExperimentCard`) per run: a multi-column
  grid in schema order beneath a live **preview band** — Voltage and Current
  (and Temperature once that column exists) against Time, drawn from the
  current draft through a ~120 ms coalescing timer, hidden while the empty
  run's CSV dropzone shows (the dropzone itself gains a dashed accent
  affordance only while a usable file drag is over it). The parameter list
  mirrors the grid's schema order: a missing schema array renders as a muted
  "not in file" placeholder row (clicking focuses its column, writing
  nothing; a reference ghost row for the same key wins), custom keys follow
  in file order and alone keep Move up/down. The bare `Validation` node
  lists one navigable row per run — its count equals those rows — and its
  "+ Add" opens the experiment-name popup. **Compare…** opens a modal,
  stateless viewer titled `Compare · <run>`: a "Compare with" rail of the
  active document's other runs (committed values, the compared run
  excluded), the bundled About:Energy sample runs, and any file opened into
  the dialog — every group under an origin caption, the samples' CC BY-SA
  4.0 provenance stated at the rail foot. Charts overlay up to four picked
  runs plus the card's own draft (labelled `<stem> · <run>`, never "You");
  an explicit run selector drives Table mode; chips are legend and removal
  only. The word "reference" never appears in this dialog — it belongs to
  the pinned-reference system.
- **Inspector** — the selected parameter's work surface, one scrolling page:
  the editing card for its kind on top (tables plot a live chart preview
  beside the grid), then an **Issues** section that appears only while the
  parameter has issues, then a resident collapsible **Documentation**
  section (future parameter tools add sections here, not new pages). Large
  grids expand in place within the pane, hiding the sections while
  expanded; floating windows are reserved for read-only visualisation, such
  as the validation-run comparison charts. A card's ( i ) opens a quick
  documentation popover; the Documentation section carries the full prose.
  A function-expression value gets the same chart: `bpx.Function` itself
  evaluates it (`core.bpx_gateway.sample_function`), never a hand-rolled
  reader of the expression. Its x domain is a plain view control, defaulted
  to 0–1 and never written to the document, and the curve reflects only the
  last **committed** value, resampling on a domain edit or a fresh commit,
  never a keystroke. A pinned reference whose own value at that key is also
  a function string overlays as a second named curve, sampled the same way
  over the same domain.
- **Diagnostics page** — a summary strip over one scrolling stream of
  per-section groups, each holding a section's issue rows and incomplete
  rows under a foldable header. The strip's chips double as view-only
  filters that never change any reported count. `core/page_buckets.py`
  supplies the one grouping that the strip and stream both render from, so
  they cannot disagree.
- **Source page** — the document's raw JSON, painted rather than edited: the
  page holds no input widget, ever, and every mutation it offers goes through
  the same commands the Editor uses. Sections fold under a `Key · N parameters`
  header; a dict-valued parameter closes to a one-line stand-in. Docking a
  reference splits it into two aligned panes — rows matched line by line, a key
  missing on one side drawn as a grey gap the height of the taller side,
  reference-only content in purple, differing values chipped. The gutter
  between the panes belongs to one affordance: a `←` on every row whose value
  could come from the reference, copying that raw value across as **one undo
  entry** on the shared stack (a reference-only section pulls whole). It is
  absent entirely when the main document is open read-only — pulling is made
  impossible, not merely undoable. One reference shows at a time, chosen from
  the badge strip in the reference pane's header; pull and Reload both act on
  the selected badge, never on the first pin. A reference that changed on disk
  is named in a slim band under the headers, checked when the page is entered
  or the window activated — never watched, never silently refreshed.
- **Workspace page** — a shaded rail beside a white pane. The rail carries
  one verb, New workspace, over two groups (Workspaces, then Recent), each
  hidden whole whenever it has no rows; a shown group's rows carry a glyph
  for their shape (the ▌ bar only when a main is recorded), an "open now"
  pill on whichever workspace is current, and hover-revealed actions — the
  app's idiom in place of a ⋯ menu. Nothing about *files* is in the rail:
  opening one and starting one are acts on the workspace that is on the
  board, so they live on the board. The pane carries the workspace's name
  (click to rename, refused inline if the name is in use), then the
  **board**: the main card beside four reference slots. The slots *are* the
  drawn cap, so there is no counter and no dock buttons — at four there is
  simply no ＋ left to click. Each card offers a route out so the page is
  never a dead end ("Edit its parameters ▸", "N errors · why? ▸", "N values
  differ ▸"). A workspace whose files have moved opens anyway, with a banner
  naming each one and offering Locate…/Remove. Provenance stays visible
  after pinning: a slot's tooltip names its origin (the file's path, or
  "Reference library"), and the expanded record's From row either shows the
  path with its captured disk facts or names the Reference library and
  expands the derived-from-PyBaMM provenance statement; the record's Read
  as / Checked rows expand their consequence sentences (YAML comments,
  legacy conversion) exactly like the main document's record.
- **The start surface** — with no main open, the Main slot carries every way
  to fill it inline: "Open a file…", the recent files that still exist
  beneath it (the same act, pre-filled), then the New-document models each
  beside its descriptor. Flat white chips, no popup and no dashed
  placeholder. Because it exists only while the slot is empty, New document
  has no replace guard — it can only ever be born into an empty workspace —
  and Ctrl+O or a drop is what swaps a main that is already filled. A
  scaffold, once created, shows its filename with a muted "unsaved" tag
  (neutral, never amber). This is also the first-launch view.
- **Toolbar and status bar** — Save, Export (JSON/YAML), Undo, Redo and
  Search sit on the right of the top bar; opening files lives on the
  Workspace board. The status bar carries the file name and its
  Saved/Unsaved-changes state.

## Interaction conventions

- All navigation goes through `NavigationService`; search and validation
  navigate, they never filter or hide the structure.
- A pinned reference wears one identity everywhere — the same letters in the
  same colour on the Source badge strip, the card ledger, the chart legend and
  the spread scale (`ui_qt/reference_identity.py`). Colour is never the only
  thing telling two references apart, so every badge carries its letters too.
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
