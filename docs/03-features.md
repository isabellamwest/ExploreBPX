# Explore_BPX — Features

Per-feature reference for Explore_BPX. Builds on [00-project.md](00-project.md),
[01-architecture.md](01-architecture.md) and [02-ui.md](02-ui.md).

**Status is tracked per capability**: **Implemented** (in the codebase) or
**Planned** (accepted design, not yet built). The capability matrices give the
implementation status of the whole app without inspecting the codebase.
Speculative ideas live in [05-future.md](05-future.md).

Each feature is a capability table plus condensed architecture/rationale notes —
just what's needed to make a correct fix without re-deriving decisions from code.

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

Loading brings a BPX file into the application as an editable document,
accepting valid, invalid and incomplete files alike — inspecting and
repairing broken files is a core purpose of the tool.

### Capabilities

| Capability | Status |
|---|---|
| Open JSON or YAML BPX files | Implemented |
| Open invalid and incomplete files as editable documents | Implemented |
| Open File as a Workspace-page action | Implemented |
| Recent documents | Planned |

### Behaviour and Architecture

The user opens a `.json`/`.yaml` file via the **Open File…** button on the
Workspace page (`app/ui_qt/workspace_panel.py`; there is no toolbar Import
menu). Loading produces a `BPXDocument` from bytes via `core/bpx_gateway.py`,
the only module that imports `bpx`. The raw dictionary is the editable source
of truth; the object tree and validation issues are derived from it (Document
Lifecycle, [01-architecture.md](01-architecture.md)). Loading never requires
successful validation — validation runs against a copy of the raw dict and its
result is stored as derived issues, never a load gate — so invalid files still
open, with problems surfaced through validation.

### Design Rationale

Open File lives on the Workspace page, not a toolbar menu, so the page can
grow into the hub for document- and workspace-level information (title,
description, references, BPX version, model) and Recent documents without a
toolbar redesign.

Future: external database/library sources (e.g. LIIONDB) as anti-corruption
adapters mirroring `bpx_gateway.py`; Recent documents. See
[05-future.md](05-future.md).

---

## 2. Tree Navigation

The tree presents the document as a navigable hierarchy of BPX objects (never
individual parameters) and remains visible at all times; it only reveals, never
filters or collapses in response to search or validation.

### Capabilities

| Capability | Status |
|---|---|
| Derived object tree built from the raw BPX data | Implemented |
| Object selection drives the parameter list | Implemented |
| Validation markers on the lowest visible affected object | Implemented |
| Two-tier selection: object path and optional parameter path | Implemented |

### Architecture

The tree is derived by walking the actual raw data rather than the schema, so
BPX polymorphism (SPM/SPMe/DFN/Partial, single/blended electrodes) is
expressed naturally by the data shape — this also keeps the tree correct
across model variants without special-casing each one. `core/tree_model.py`
produces a UI-neutral tree of `TreeNode` objects; `ui_qt/tree_model.py` adapts
it to Qt. Selection updates `state.active.selected_path` on `DocumentSession`
(two-tier: object path, optional parameter path). Validation markers appear on
the lowest visible object containing an issue; ancestors do not duplicate it.
The tree subscribes to `NavigationService` notifications and expands ancestors
of a navigation target rather than owning navigation logic.

Future: multi-document workspaces and comparison navigation reuse the same
tree and navigation service. See [05-future.md](05-future.md).

---

## 3. Parameter Inspection

Parameter inspection presents the direct parameters of the selected object
and, for a selected parameter, a detailed view including value, unit, schema
description and validation state.

### Capabilities

| Capability | Status |
|---|---|
| Parameter list for the selected object | Implemented |
| Parameter selection drives the Inspector | Implemented |
| Inspector shows value, unit and schema metadata | Implemented |
| Parameters classified by kind (scalar, integer, enum, function, table, unknown) | Implemented |
| Parameter information popover ( i ) surfacing rich BPX metadata | Implemented |
| Self-contained ParameterCard (title, validity badge, summary description in the card) | Implemented |

### Behaviour and Architecture

The parameter list shows direct parameters of the selected object only; the
Inspector is the selected parameter's work surface and the home for all
parameter-centric tools, added as tabs in its secondary workspace (see
[02-ui.md](02-ui.md)). Parameters are `ParameterItem` objects owned by a
`TreeNode`. Classification into `ParameterKind` (`core/parameter_types.py`) is
declared-type first: schema metadata is authoritative and a value's runtime
type never changes which editor opens, so an invalid stored value (e.g. a
string in a float field) is still inspected/edited as its declared kind rather
than falling back to a raw/read-only view. The `meta=None` contract for
user-defined/custom parameters (metadata absence is a valid first-class state;
value shape classifies when metadata is genuinely absent) is defined in
[01-architecture.md](01-architecture.md).

Rich parameter *documentation* — physical meaning, units, accepted types,
functional dependence, model availability, measurement methods, specification
links, symbols — is delivered on demand through an information popover
anchored to the self-contained ParameterCard (title, validity badge, summary
description all in the card), triggered by an ( i ) affordance, fed by a
unified parameter-metadata provider (`core/parameter_metadata.py`) combining
`FieldMeta` with the educational-metadata dataset
(`core/parameter_descriptions.py`, `app/data/parameter_descriptions.yaml`,
`ui_qt/documentation_tab.py`).

### Design Rationale

Making the Inspector the single parameter work surface — rather than a
separate detail page per concern — keeps editing, analysis and documentation
composed over one selected parameter.

Future: Analysis and References sections over the selected parameter — see
[Analysis and Visualisation](#9-analysis-and-visualisation) and
[05-future.md](05-future.md).

---

## 4. Editing

Editing changes parameter values in the raw working document — the
foundational capability of the app ([00-project.md](00-project.md)) — and is
designed to accept invalid work-in-progress input so broken files can be
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
| Declared-kind taxonomy (text, boolean, map, series; table narrowed to `InterpolatedTable`) | Implemented |
| Mode strip on union-typed fields (verbatim BPX vocabulary, per-mode drafts, conditional Raw) | Implemented (`FUNCTION` and `MAP`) |
| Raw JSON editor with a commit gate (refuses a draft with no representation) | Implemented |
| Parameter symbol shown beside the card title (rendered maths, from the descriptions dataset) | Implemented |
| Text editing (auto-growing, Shift+Enter newline, pattern hint) | Implemented |
| Boolean editing (toggle) | Implemented |
| Per-material map editing (keys seeded from sibling Particle names; duplicate keys blocked) | Implemented |
| Series inline grid (raw-object cells, add/remove row, no coercion) — for a list-valued parameter outside a Validation run | Implemented |
| Table inline grid (x/y grid over a live preview) | Implemented |
| Expanded (takeover) grid editor — Expand/Collapse grows the grid to fill the pane | Implemented |
| Paste into a grid (Ctrl+V or right-click; delimiter auto-detect, header skip, preview, replace/append, no coercion) | Implemented |
| Unified `ExperimentCard`: one multi-column grid for a Validation run's Time/Current/Voltage/optional-Temperature arrays, every column always editable, focused column set by which path navigation resolved | Implemented |
| "+ Temperature [K]" toolbar action adds the run's optional array in one step | Implemented |
| Import-first empty state for a run with no data yet (CSV dropzone + Browse, "or type values directly", dismisses on the first value) | Implemented |
| Guided empty state for a Validation section with zero runs ("+ Add experiment", "Import CSV as new experiment…", two undo steps) | Implemented |
| CSV import (inline button, always-shown mapping dialog; an experiment's own columns fill in one undo step; x/y table → positional mapping, both required) | Implemented |
| "Compare…" dialog (card toolbar, always visible): overlay the card's live draft against reference runs — bundled About:Energy sample cells (NMC pouch + LFP 18650, 5 runs each) or any BPX file via "Open BPX file…" — by chart or table, with a key-numbers summary (points, duration, current/voltage range); picker selection = bordered box + small tick (no circled badges, standing rule); an empty run states "no data yet" plainly; read-only, no persistence | Implemented |
| Remove parameter (row context menu, Delete key) | Implemented |
| Tree editing (add/remove sections; add/rename/remove materials and experiments; confirm before removing populated content) | Implemented |
| Enhanced function-expression editor (syntax highlighting, validation) | Planned |
| Model switch completes structure (adds required sections empty; removes nothing; one undo step) | Implemented |
| Value preview in the parameter list (raw-verbatim, elided, full value on hover) | Implemented |

### Commit contract

Editing happens in per-kind cards in the Inspector, selected by
`ParameterKind`, not parameter name. The user edits, presses Enter to commit
(valid or invalid) to the raw working document — validation re-runs — or
Escape to revert the uncommitted draft.

- **Enter commits** the current raw input, valid or invalid — commit is never
  gated on validity, only (for the Raw JSON editor, see below) on
  representability. **This is the only commit trigger**: blur does not
  commit, and there are no detached footer Apply/Reset buttons.
- **A discrete pick commits immediately**: choosing an entry from an enum's
  opened dropdown, or clicking a boolean's checkbox, is a complete act and
  applies without a further Enter (this is how `Header.Model` is switched).
  Arrowing through an enum's values on the *closed* combo remains a draft —
  step-through is browsing, not choosing.
- **Escape reverts** the uncommitted draft.
- Cards emit raw user input and never gatekeep values; invalid data is
  surfaced as validation issues after revalidation, not blocked at the card.

### Input system

One card skeleton per `ParameterKind` (title, authoring flag, validity badge,
( i ) info affordance; mode strip when the declared type is a union; value
area; hint line from `FieldMeta.examples`; description).

- **Kind is declared; mode is chosen.** The schema's declared type fixes one
  `ParameterKind`. Union-typed fields carry a **mode strip** naming each legal
  representation in verbatim `bpx` schema vocabulary — `FloatInt` ·
  `Function` · `InterpolatedTable` for `FloatFunctionTable`; `FloatInt` ·
  `dict[str, FloatInt]` for per-material fields — never translated. The
  stored value's shape picks the initial mode; only that mode is seeded, since
  switching mode *completely changes* the value (`3.7` → `InterpolatedTable`
  gives an empty grid, never a fabricated one-row table) — there is no
  seeding between modes. Each mode keeps its own draft until commit or
  Escape; commit writes only the active mode's value. **Switching mode is not
  itself an edit**: it does not mark the card dirty, does not trigger live
  validation, and a bare Enter after it commits nothing; Escape reverts value
  *and* mode.
- **Raw mode is conditional**, appended only when the committed value fits no
  structured mode (a ragged table, a non-numeric series entry, a `bool`, a
  list); that decision is made once at construction. Values are never
  silently coerced or discarded. The Raw JSON editor is the one card that
  gates commit on syntax: unparseable text has no value to emit, and
  committing it as a string would destroy the original structure (data loss,
  not an invalid edit), so `commit_blocked_reason` refuses it. This gate turns
  on **representability, never schema validity** — every other card commits
  invalid-but-representable input freely.
- **Empty and null.** An empty text input commits `""`; an empty numeric
  input commits `null`. A card commits only when its draft differs from the
  committed value, so a no-op Enter never rewrites a stored `null`. No
  reachable BPX field is nullable, so there is no *Set to null* affordance —
  removing the key is the separate Remove-parameter action.
- **Large values.** Series/table cards use a compact inline grid with
  **Expand**/**Collapse**, first-class paste, and an **Import CSV…** button
  with an always-shown mapping dialog (non-numeric cells kept as text, never
  zero-filled). A Validation run's own Time/Current/Voltage/optional-
  Temperature arrays are edited together in one multi-column `ExperimentCard`
  (`cards/experiment.py`) rather than one series card per array: every column
  stays editable regardless of which one navigation focused, a typed cell
  commits only the column that changed, and CSV import auto-matches the run's
  own columns by header/position — both in one atomic `SetValues`. An x/y
  table maps columns *positionally* (never `auto_map`'s substring rule,
  unsafe for one-letter `x`/`y`), both required, and commits as a normal card
  draft.
- **Grids hold raw uncoerced objects, not numbers.** `NumericGrid`
  (`cards/values.py`) cells are the same lenient values line editors emit: a
  typed `oops` stays `"oops"`, a blank cell is `None`, neither is ever
  coerced — the validator reports the type error. A card is read-only only
  when the stored value has *no* grid representation at all (dict, nested
  list, `bool`). The validator tints the cell it blames for element-level
  diagnostics; edits clear stale tints immediately. A grid carries a live
  numeric-only preview (`QtCharts`, degrades gracefully if unavailable).

### Architecture

Editing is command-based: `core/commands.py` describes intent,
`core/editing.py` performs pure raw-dict mutation, `core/command_service.py`
previews/executes with structural guardrails, `DocumentSession` records
undo/dirty state. A card commit is a `SetValue` command on the same undo
stack as structure edits (`AddSection`, `RemoveSection`, `RenameKey`). A
multi-parameter edit (CSV import filling a Validation run's arrays) is one
`SetValues` command — one undo entry, all-or-nothing. `RenameKey` (user-named
dict keys only, gated by `structure.can_rename`) preserves key order and
moves the *address* of every descendant; values referring to the old name
(a per-material MAP key) are deliberately left for the validator to report,
not rewritten. A card's contract is fixed: it edits one `ParameterItem`,
emits raw input, never decides validity — `ExperimentCard` is the deliberate
exception, editing every array of a Validation run in one widget instead of
one `ParameterItem` per card, still committing a single `SetValues` per Enter
that touches only the columns whose draft changed. The Inspector routes any
parameter or bare node under a Validation run to `ExperimentCard`; `SeriesCard`
(`cards/series.py`) remains the single-column series editor, now reached only
by a list-valued parameter outside a Validation run. See
[01-architecture.md](01-architecture.md).

**Undo restores the selection too**: each undo entry stores the selection
current when the command ran, so undo navigates to what it reverted.

**Undo/Redo have two surfaces, deliberately unlike each other.** The toolbar
buttons are document commands: act regardless of focus, grey out when
inapplicable. `Ctrl+Z`/`Ctrl+Y` (and `Ctrl+Shift+Z` where not already a
platform Redo binding) are **focus-aware**, since a window shortcut is
matched before the focused widget sees the key: (1) a focused text editor
with typing of its own — undo/redo that typing; (2) otherwise a focused card
with an uncommitted draft — do nothing (reverting/reapplying past it would
change an off-screen parameter; Escape/the toolbar remain available); (3)
otherwise, undo/redo the document. Committing rebuilds the card with no
typing history or draft, so the next `Ctrl+Z` reaches the document. A new
command clears the redo stack.

**Switching model completes the structure.** Committing `Header.Model` routes
through `ChangeModel`: the value and the target model's required-but-missing
sections (added empty) arrive as one atomic step/undo, so the validator
reports missing parameters field by field instead of one opaque root error.
Nothing is removed — an unrecognised section stays as an extra input, dropped
only via the tree's confirm-gated Remove section.

### Design Rationale

Enter-to-commit with co-located cards replaced detached footer buttons and
blocking invalid commits (which contradicted supporting invalid BPX files);
per-keystroke/blur commit was rejected as surprising.

**Kind is declared, mode is chosen** — schema type is fixed and authoritative;
mode is a user choice over representation, never inferred from runtime shape.
This is why only the initial mode is seeded and no draft carries between
modes: seeding a different mode would fabricate data the user never entered.

Future: enhanced function editor (above); broader authoring-driven editing
states in [Authoring](#8-authoring).

---

## 5. Validation

Validation continuously reports whether the raw working document satisfies
BPX/schema rules, guiding the user to problems without locking the editor,
and keeps schema validation strictly separate from any future plausibility
checking.

### Capabilities

| Capability | Status |
|---|---|
| Continuous BPX schema validation via the `bpx` package | Implemented |
| Normalised `ValidationIssue` records (path, message, severity) | Implemented |
| Best-effort mapping from validation paths to visible objects/parameters | Implemented |
| Diagnostics workspace listing all document issues | Implemented |
| Parameter-scoped Issues tab in the Inspector secondary workspace | Implemented |
| Keyboard navigation of issues (Enter-to-activate) in the Diagnostics workspace and Issues tab | Implemented |
| Outstanding section on the Diagnostics page (required + optional-null completion tasks, `core/completion.py`) | Implemented |
| Absorption of validator diagnostics already accounted for by an Outstanding task, shown as muted secondary text on that row | Implemented |
| Union-pair display merge (both the `float_type`/`int_type` and `float_parsing`/`int_parsing` variants) across Issues, Outstanding and the Issues tab | Implemented |
| Rail badge reflects post-absorption, post-merge Issues count only | Implemented |
| `IssueKind` classification for actionable remediation | Planned |
| Pure remediation functions (edit, move, choose model, map materials, add section) | Planned |
| Restored field paths for root-landing warnings | Planned |
| Optional warning hide/ignore for intentional modelling decisions | Planned |

### Behaviour

Validation runs continuously. Issues are visible in two places: the
**Diagnostics workspace** (activity bar) lists **all** issues, including
document-/object-level ones; the **Issues tab** (Inspector secondary
workspace) shows issues for the **currently selected parameter only** and
never document/object-level ones. Both are keyboard-drivable (arrow to
select, Enter/double-click to navigate — selection alone never navigates,
keeping the editor spatially stable, mirroring SearchPopup's
Up/Down/Enter); focus stays in the list after activation.

The Issues tab follows the secondary workspace's **workspace-state** model:
starts collapsed, tab strip always visible, badge (`Issues`/`Issues (2)`)
updates live whether or not the panel is open; changing selection while open
refreshes without closing; only the user collapses it.

#### Issues and Outstanding (Diagnostics page)

`core/page_buckets.py` buckets the document's post-absorption diagnostics and
completion tasks (`core.completion.document_completion`) by owning section —
one `SectionBucket` per rail entry, in document order, a Document bucket
first when occupied — so the Diagnostics page's strip/rail/pane and the
activity-bar badge all read from one shared grouping instead of re-deriving
it. Selecting a rail entry shows that bucket's own Issues and Outstanding as
two group boxes:

- **Issues** lists every validator diagnostic bucketed there, not accounted
  for by an authoring task (see [Authoring](#8-authoring)); its box-header
  badge shows red/amber counts, matching the rail.
- **Outstanding** lists the bucket's completion tasks: a header ratio
  (`Outstanding · N of M remaining`, `· section absent`, or one or more
  required child sections still absent reported as `N sections absent`
  instead of a misleading `0 of 0`) covering Required tasks, followed by a
  quieter optional sub-head for Expected-but-optional fields committed
  `null`. Either may be absent; under `Partial` (nothing ever Required) it
  shows the fixed notice pointing to per-section parameter-list suggestions
  instead.

Selecting **"All sections"** (the default) instead shows every bucket at
once — the reconciliation backup view: one foldable header per
bucket (same badges as the rail) over its issue rows then its outstanding
rows, so nothing on the page can ever go missing between the two views.

The strip's chips and text field filter both views, **view-only**: hiding
rows never changes a count (buckets, badges, ratios and the app badge stay
post-absorption truth), the ✓ empty states never stand in for hidden rows,
and a muted `N hidden by filters` line accounts per view for what the
filters hid. Filter state is per-session panel state — never persisted,
reset on a new document.

A committed `null` is Outstanding whenever the field is schema-**Expected**,
not only Required (creating an expected field and leaving it unfilled never
makes the document look worse; the REQUIRED tag still only renders for
Required fields). A **custom** parameter (no schema entry) is the deliberate
exception and stays a plain Issue — its `extra_forbidden` rejects the *name*,
not the emptiness.

**Absorption.** A diagnostic moves from Issues into Outstanding — **absorbed,
never dropped** — exactly when an Outstanding task already accounts for it (a
`missing` diagnostic at a task's own missing field/section; any diagnostic on
a parameter with a task's committed-`null` field, including both diagnostics
of a null union field; the root `State`-demand diagnostic when a `State`-absent
task exists). **Every absorbed diagnostic still renders**, on its Outstanding
row as muted secondary text carrying its real, verbatim message — the
validator is never silenced, every diagnostic appears in exactly one of
Issues or Outstanding, and the rule only ever *moves* a diagnostic, never
changes what the validator judges wrong.

A single bad `FloatInt` raises two diagnostics (`float_type`/`int_type`, or
`float_parsing`/`int_parsing`); this pair always **displays as one row**
across Issues, Outstanding's secondary text, and the Issues tab — a display
merge only, the validator's own output and `parameter.issues` are untouched.

The **rail badge** (activity bar Diagnostics icon) counts Issues only,
**post-absorption and post-merge**: a fresh skeleton or a document with only
added-but-unfilled Expected fields shows no red badge. **Parameter-scoped
surfaces are unaffected by absorption** — the Issues tab and a parameter's own
validity badge report the validator verbatim (message, severity) even for
diagnostics the Diagnostics page has absorbed, so a parameter's inline state is
never silently downgraded; they still apply the same float/int merge.

### Architecture

Validation runs from the raw dict via `bpx_gateway.validate` on a copy,
producing normalised `ValidationIssue` records. `core/tree_model.py` maps
issue paths to the nearest visible `TreeNode`/`ParameterItem` by best-effort
suffix matching (pydantic locations don't always match visible BPX paths;
some warnings currently land at the document root — restoring their field
paths is Planned, tied to the warning-path gap in
[01-architecture.md](01-architecture.md)). `IssueKind` classification and pure
remediation functions are Planned.

The Outstanding section and the rail badge are both derived from one
`core.completion.partition_issues(document, tasks)` call per refresh, so they
can never disagree. It is the only function in `core/completion.py` that
reads `ValidatorDiagnostic`s: it consumes the document's attached diagnostics
plus `document_completion`'s task list and returns absorbed-vs-visible
diagnostics and post-absorption counts. See [Authoring](#8-authoring) for why
completion cannot be derived from diagnostics alone. Dependencies:
`core/bpx_gateway.py`, `core/validation.py`, `core/tree_model.py`,
`core/completion.py`, `NavigationService`.

Future: plausibility/sanity validation against known cell parameter ranges, a
separate layer with its own reference dataset, independent of schema
validation. See [05-future.md](05-future.md).

---

## 6. Search

Search is navigation, not filtering: it lets the user jump to any object or
parameter by name or path without altering document structure.

### Capabilities

| Capability | Status |
|---|---|
| SearchPopup navigation over objects and parameters | Implemented |
| Focus by `Ctrl+F` and `Ctrl+P`, selecting existing text | Implemented |
| Keyboard navigation (Up/Down, Enter, staged Escape) | Implemented |
| Result activation through `NavigationService` | Implemented |

### Behaviour and Architecture

The search box (toolbar) is focused by `Ctrl+F`/`Ctrl+P`, selecting existing
text. Results appear in a custom **SearchPopup** (not `QCompleter`), indexing
both navigable objects and parameters, each shown as name over full path;
scrolls after ~8 results; Up/Down/Enter/Escape, with Escape staged (close
popup → clear search → return focus). Search never hides tree nodes or
parameter rows. It consumes the same object/parameter index used for
navigation and activates results exclusively through `NavigationService`
(see [01-architecture.md](01-architecture.md), [02-ui.md](02-ui.md)),
owning no navigation logic of its own.

### Design Rationale

Search is navigation, not autocomplete/filtering — a flat-string `QCompleter`
fought the interaction design, so a custom SearchPopup gives one owned
surface reaching objects and parameters, at the cost of more initial work
than reusing a completer. No ranking/icons/recent-searches/grouping yet,
deliberately, until there's concrete need.

Future: ranking, icons, recent searches, and searching validation/comparison/
database results through the same surface. See [05-future.md](05-future.md).

---

## 7. Save and Export

Save and Export are distinct operations over the raw working document: Save
persists to the current file, Export writes a copy. Keeping them distinct is
what makes the Modified/Saved state meaningful.

### Capabilities

| Capability | Status |
|---|---|
| Export / round-trip to JSON or YAML | Implemented |
| Dirty / backing-file state on `DocumentSession` | Implemented |
| Distinct Save (write back, clear Modified) vs Export (write copy, no state change) | Implemented |

### Behaviour and Architecture

Save and Export are separate toolbar actions (see [02-ui.md](02-ui.md)). Save
writes back to the current backing file and clears the Modified indicator;
Export writes a copy to a chosen path/format and does not change Modified
state. The status bar reflects the resulting state. Both serialise the raw
working document via `core/export.py`, deliberately including invalid
work-in-progress data (so a broken file can still be exported for sharing or
repair). `DocumentSession` owns the dirty flag and backing-file path that
distinguish the two operations.

### Design Rationale

Save and Export are genuinely different operations; conflating them would make
the Modified/Saved indicator meaningless. Export is also the seam that later
generalises to simulator hand-off writers.

Future: simulator hand-off targets (e.g. PyBOP, PyProBE), target-specific
writers behind the export layer, compatibility checks. See
[05-future.md](05-future.md).

---

## 8. Authoring

Authoring covers the lifecycle of creating, completing and maintaining BPX
documents — broader than editing individual values: it owns the distinction
between **Complete BPX** (ready for simulation/downstream use), **Incomplete
BPX** (genuine work-in-progress), **Skeleton** (model-specific structural
starting point, no invented scientific values) and **Template** (a reusable
skeleton or partial document with trusted defaults for a lab, organisation,
chemistry or workflow), and keeps completion state separate from validation
state. Authoring is an accepted **core product capability and a major
implementation priority**, designed alongside editing rather than deferred
([00-project.md](00-project.md)); only Upload/open skeleton workflows and
Save as Template / New from Template remain Planned.

Completion uses fixed terminology, distinct from validation's valid/invalid:
**Expected** — the schema names the field for this section. **Required** —
the schema requires it and the model is one of SPM/SPMe/DFN. **Missing** — a
Required field with no entry in the raw document. **Outstanding** — a
Required field that is Missing, or *any* schema-Expected field (Required or
not) committed as literal `null` — creating an expected field and leaving it
unfilled never makes a document look worse, so the calm Outstanding
treatment does not depend on requiredness. A **custom** parameter (no schema
entry at all) is never Outstanding: its problem is the name BPX rejects, not
the emptiness, so it stays a plain Issue. "Valid"/"invalid" never describe
completion state; those words belong to validation alone.

### Capabilities

| Capability | Status |
|---|---|
| Raw-dict model that represents invalid and partially edited documents | Implemented |
| Incomplete structural scaffolds without invented values (`document_factory.py`) | Implemented |
| Continuous validation that tolerates work-in-progress editing | Implemented |
| Add a freeform custom parameter to a section (no synthesised metadata) | Implemented |
| Add a known BPX parameter via search (section-expected + full-schema fallback) | Implemented |
| New BPX from built-in model skeletons (SPM, SPMe, DFN, Partial) | Implemented |
| Completion status distinct from validation status | Implemented |
| Completion view (Outstanding section) for unfinished required authoring work | Implemented |
| Expected-but-missing parameter rows ("N fields to add") in the parameter list | Implemented |
| Upload/open skeleton workflows | Planned |
| Save as Template and New from Template workflows | Planned |

### Behaviour

The user starts from a model skeleton, then fills what the app shows is
missing. Two surfaces share the same completion query: a collapsed "N fields
to add" group at the foot of each section's parameter list, and the
Diagnostics page's Outstanding section (§5, Issues and Outstanding), grouped
by section into a required and a quieter optional sub-group. Activating a
row navigates to it and, where nothing exists yet, performs the one enabling
step first — a missing field's `+` adds it with `null` and focuses its
editor; an absent section's action adds it; an undeclared model's action
reveals `Header.Model` — all in one undo step. A field the app itself added
but not yet filled is Outstanding, never a red Issue.

Parameters are added from a section-scoped "+ Add parameter" header
([02-ui.md](02-ui.md)); the popup lists expected BPX aliases and, on search,
other schema aliases (greyed) plus a "Create custom parameter" fallback.
Every add writes an empty value through `AddParameter` and reveals the row
via `NavigationService`; nothing is fabricated. An undeclared/unrecognised
`Header.Model` collapses every completion surface to a single "declare a
model" task revealing `Header.Model` (the one group that survives, since
Header's fields don't vary by model); `Partial` suggests every Expected
field but marks nothing Required, since its schema forbids most of what a
concrete model would require.

### Architecture

Completion is a **pure, stateless projection over `(raw, model)`** —
`core/completion.py`, the same shape as `structure.addable_child_sections`. It
never persists state or judges legality (the validator remains sole
authority), and recomputes fresh from the committed raw dict, never drafts.
`completion_for(path, value, model)` returns a section's fields-to-add;
`document_completion(raw)` aggregates document-wide Required-only tasks;
`partition_issues(document, tasks)` — the only function reading validator
diagnostics — splits them into absorbed vs visible.

Completion cannot be read off validator diagnostics: `bpx`'s `mode="before"`
validators short-circuit (a section-level one can raise before pydantic
checks that section's required fields, leaving diagnostics byte-identical
after deleting a required field; the root validator stops pydantic
validating `State`/`Validation` once `Parameterisation` has a problem, hiding
even the root demand for `State`). An absent section always collapses to one
`missing` diagnostic — required leaves never enumerated — and an
absent/unrecognised `Header.Model` yields one diagnostic with
`Parameterisation` never validated. Completion instead reads the schema and
raw dict directly.

`core/document_factory.py` creates incomplete structures without scientific
defaults. Authoring-created custom parameters do not synthesise or persist a
`FieldMeta` (`meta=None`, [01-architecture.md](01-architecture.md)); the
validator is the source of truth for their legality. The export guarantee is
absolute: authoring/completion state never forces fake scientific values
into simulator-facing output — skeletons provide structure only.

### Design Rationale

A work-in-progress document is not the same state as an incorrect one:
collapsing unfinished authoring work into generic validation failure would
mislead the user, and inventing values to look complete would corrupt
exported data. Treating authoring as a first-class lifecycle — with
completion distinct from validation — costs a second document-status concept
needing careful UI language, but the alternatives (treating incomplete as
invalid, placeholder values, merging completion into validation) were
rejected as dishonest or confusing.

Future: org/lab/chemistry/workflow-specific templates, session change
awareness, a Changes review workspace, provenance/confidence tracking,
reusable parameter packs. See [05-future.md](05-future.md).

---

## 9. Analysis and Visualisation

Analysis and visualisation present a selected parameter graphically (e.g.
plotting a function or interpolated table) — a parameter-centric tool hosted
in the Inspector, not a separate workspace.

> **Specification status.** Intentionally underspecified: the accepted design
> is limited to the placement decision (launcher tab in the Inspector
> secondary workspace) and the initial subject (function/table
> visualisation). Detailed behaviour awaits a dedicated design pass and must
> not be invented before then.

### Capabilities

| Capability | Status |
|---|---|
| Analysis as a tab in the Inspector secondary workspace | Planned |
| Launcher model: per-tool `Show` actions that open floating visualisations | Planned |
| Function and interpolated-table visualisation (for example OCP plots) | Planned |

### Behaviour and Architecture

With a parameter selected, the Analysis tab (Inspector secondary workspace,
never an activity-bar workspace) lists the visualisations available for it
(e.g. `OCP Curve`, `Diffusivity`, `Conductivity`, `Statistics`), each with a
`Show` action; selecting one opens/toggles a floating graph/dialog. The tab is
a **launcher** only — it never hosts a large embedded graph. Analysis consumes
the selected `ParameterItem` and evaluates expressions/tables via
`core/bpx_gateway.py`'s `to_python_function()`, attaching at the Inspector
secondary-workspace tab seam ([01-architecture.md](01-architecture.md)). No
analyzer registry is built before concrete analyzers exist — the first
analyzers should be implemented directly against the tab seam.

### Design Rationale

Analysis is parameter-centric, so it belongs in the Inspector, not the
activity bar or editing cards. The launcher model keeps the tab compact while
still giving access to rich visualisations through floating dialogs; a
registry before analyzers exist is premature. The cost is that floating
dialogs need their own lifecycle/positioning conventions, defined when the
first analyzer is designed.

Future: parameter-centric plausibility displays, docking/maximising floating
visualisations, comparison overlays for related files or known cells. See
[05-future.md](05-future.md).
