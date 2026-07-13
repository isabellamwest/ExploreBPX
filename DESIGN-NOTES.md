# Explore_BPX — Design Notes & Evolution

A record of the design decisions behind Explore_BPX: the questions that were
open, how they were resolved, the rules that changed as the product matured, and
the order the system was built in. The `docs/` specification describes the app as
it *is*; this document explains *why it is that way* and *what it used to be*.

Explore_BPX is a PySide6 desktop application for exploring, editing, validating
and authoring [BPX](https://www.faraday.ac.uk/get-involved/faraday-battery-challenge/bpx/)
(Battery Parameter eXchange) files. It delegates all schema and validation
semantics to the official `bpx` package and owns only the human interface: a
derived object tree, per-kind parameter editors, continuous validation surfaced
against the raw document, and authoring from model skeletons.

---

## 1. Design decisions that changed

### Union-typed fields are one kind with a mode strip

**Earlier rule:** for a `FloatFunctionTable` field (which may legally hold a
number, a function expression, or an interpolated table), the *stored value's
shape* selected among distinct scalar / function / table editor kinds.

**Problem:** shape-driven classification made a field's other legal
representations unreachable from the UI. A field currently holding a scalar
could never be turned into a table, because nothing in the interface offered the
other modes.

**Now:** the union is a single kind. Its card carries a **mode strip** naming
each legal representation in verbatim `bpx` schema vocabulary; the stored value's
shape selects only the *initial* mode, and the user switches freely. Value shape
still classifies in exactly two places — metadata-absent parameters, and
undeclared dicts/lists whose topology no schema field describes.

### Context menus may create at container level

**Earlier stance:** a blanket "no context menus" rule — all creation lived in
visible header affordances, all right-click menus were forbidden.

**Refined to:** context menus never create *at row level*, and creating a
parameter is never hidden behind a right-click. But they *do* create at
*container level* — the structure tree's **Add section ▸ / Add material… / Add
experiment…** — because sections and dict-keyed collections are the containers
being filled. Row-scoped actions on existing items (Remove parameter, Rename,
Remove section) also live in right-click menus. The original blanket rule
predated the app having any row- or container-scoped actions at all.

### Popup dismissal is press-driven, not focus-driven

Transient popups (search results, add-parameter, parameter info, name entry)
dismiss on a mouse press *outside* the popup, consuming that press so one click
closes and a second click acts. Dismissal is deliberately **not** driven by
keyboard focus: focus does not move when the user presses a non-focusable
surface such as the top bar or page header, and a focus-driven rule left those
popups stranded open when the user clicked there.

---

## 2. Open questions that were resolved

### User-defined parameter metadata — the `meta=None` contract

The one design question the authoring track depended on. **Resolved:** a
user-authored custom parameter is an ordinary raw-dict entry whose `FieldMeta`
is genuinely absent (`meta=None`). Nothing is synthesised and nothing is
persisted for it. Classification stays metadata-authoritative wherever metadata
exists and falls back to value-shape classification where it is absent; absence
is a valid first-class state, and the BPX validator is the sole judge of whether
a custom parameter is legal.

Because no persistence mechanism exists or is needed, every authoring capability
that creates parameters (the raw/unknown fallback editor, the add-parameter
workflows) was built as a general "metadata-absent" capability rather than
against any specific synthesis mechanism — so broader custom-parameter authoring
remains feasible later without rework.

Locked by tests: a valueless custom parameter classifies as `UNKNOWN`, numeric
as `SCALAR`, string as `FUNCTION`; a known alias still resolves its `FieldMeta`
and stays metadata-authoritative.

### The BPX authoring lifecycle — from proposed to core commitment

Authoring whole documents (not just editing individual values) was once a
*proposed* direction. It has since been accepted as a core product commitment:
editing is foundational, authoring is a first-class priority track designed
alongside it, and completion state is tracked separately from validation. This
now lives in the project vision, the architecture, and the Authoring feature
specification rather than in any decision register.

---

## 3. Build order, as delivered

The system was built foundation-first, with editing and authoring advancing
together. Acceptance criteria below are the observable conditions that marked
each item done.

### Foundation

Document loading (JSON/YAML, including invalid and incomplete files); the
derived object tree and per-object parameter list; parameter inspection with
declared-type-first classification; scalar / integer / enum / function editing
with Enter-to-commit and Escape-to-revert; command-based mutation with undo;
continuous BPX validation with issue records; the Validation workspace and a
parameter-scoped Issues tab; save/export with distinct semantics and
dirty/backing-file state; a single `NavigationService` coordinating all
navigation; SearchPopup over objects and parameters; the `DocumentSession` /
`AppState` split; and the raw-dict model with incomplete scaffolds.

### Navigation, review and file semantics

- **SearchPopup navigation** — focused by `Ctrl+F` / `Ctrl+P`; indexes objects
  and parameters showing name over path; every activation routes through
  `NavigationService`; never hides tree nodes or rows.
- **Save vs Export** — Save writes back to the backing file and clears Modified;
  Export writes a copy without changing Modified; the status bar reflects the
  result.
- **Keyboard navigation of issues** — arrow to survey, Enter to activate through
  `NavigationService`, focus stays in the list so the user can arrow to the next
  issue; the same behaviour in the parameter-scoped Issues tab.
- **Parameter information popover** — a contextual ( i ) glance on every
  ParameterCard (physical meaning, units, accepted types, functional dependence,
  model availability, specification links, symbols) from a unified metadata
  provider combining `FieldMeta` with a separate educational source; the
  ParameterCard became self-contained (title, badge, description moved in) with
  the editing/commit contract unchanged.

### Authoring foundation

New documents from SPM / SPMe / DFN / Partial model skeletons (structure only,
no invented values); completion state tracked and displayed separately from
validation; expected-but-missing parameters as editable rows that write real BPX
only when committed; templates.

### Editing depth

- **Unknown/raw fallback editor** — `UNKNOWN`-kind parameters route to an
  editable raw card instead of a read-only dead end; a committed value
  reclassifies to its real kind on rebuild.
- **Add custom parameter** — a section-scoped "+ Add parameter" header opens a
  popup with a "Create custom parameter" row, routing through the `AddParameter`
  command with an honest empty value.
- **Add BPX parameter** — the same popup lists a section's expected aliases on
  empty input and, on search, filters those (emphasised) while surfacing other
  matching BPX aliases (greyed). The electrode single/blended union is resolved
  from the section's live content (a `Particle` key means blended; an empty
  electrode resolves to single-particle), so electrodes — and named `Particle`
  materials and `Validation` runs — enumerate expected fields like any other
  section. Container properties are never offered as parameters: adding one
  would overwrite the section it names.

### Input-system editor

The per-kind editing surface, built grid-first:

- **Undo** made command-based and undoable on the same stack as add/remove, with
  a focus-aware `Ctrl+Z` that reaches an editor's own draft first.
- **Series & interpolated-table grids** — raw-object cells (never coerced), with
  a live QtCharts preview above the grid.
- **Mode strip** for union-typed fields (FUNCTION, MAP), with per-mode drafts and
  a conditional Raw mode appended only when the committed value fits no
  structured mode.
- **Map and table editors** — per-material key/value maps (keys seeded from
  sibling Particle names, duplicate keys blocked) and x/y interpolated tables.
- **Parameter symbol** shown beside each card title, rendered from the
  descriptions dataset.
- **Expanded (takeover) grid editor** — a text Expand action grows the grid to
  fill the Inspector pane.
- **Clipboard paste** — Ctrl+V or right-click, with delimiter auto-detect, header
  skip, a preview reporting rejected cells, and Replace-all / Append. Rejected
  cells are kept as text, never zero-filled.
- **CSV import** — in the expanded editor, with an always-shown, always-editable
  column-mapping dialog; fills a Validation run's arrays as one atomic undo step;
  skipped targets are left untouched.
- **Read-only sibling columns** — a Validation run's series grid shows its
  sibling arrays as muted, non-editable columns, so a length mismatch is visible
  while editing.
- **Tree structure editing** — add/remove sections, add/rename/remove materials
  and Validation experiments via a container right-click menu; the menu offers
  only what the schema declares legal at each node; removing populated content
  confirms first; every operation is one undo step.

---

## 4. Superseded — the Design Decision register

The project once kept a numbered Design Decision register (DD-001 through DD-012)
in the UI document. Those decisions were promoted into the documents that own
their subject matter and embedded inline as design rationale:

- Workspace shell, activity bar, secondary surfaces, toolbar shape → `docs/02-ui.md`.
- `DocumentSession` / `AppState` split, navigation ownership → `docs/01-architecture.md`.
- Editing commit model, validation review and cursor behaviour, parameter-scoped
  Issues tab, SearchPopup, Save/Export semantics → `docs/03-features.md`.

The one decision that was still *proposed* — the BPX authoring lifecycle
(formerly DD-012) — was accepted as a core product commitment (see §2 above). No
separate decision register is maintained; this note exists only to explain the
history for anyone looking for the old DD numbers.
