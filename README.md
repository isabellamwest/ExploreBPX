# ExploreBPX

A desktop app that makes [BPX](https://github.com/FaradayInstitution/BPX)
(Battery Parameter eXchange) files easy to open, understand, validate, edit
and author.

BPX files are machine-readable JSON/YAML, but can be hard to inspect and
navigate by hand as they grow. ExploreBPX presents a BPX document as a
navigable tree of objects and parameters with continuous validation, a
dedicated editor for every parameter kind, and authoring support for
building new documents from model skeletons.

It builds on the official `bpx` package and deliberately implements none of
the BPX specification itself: parsing, schema and validation all come from
`bpx`, and the app's job is to surface them faithfully.

![The Editor: object tree, parameter list and inspector, editing a table
parameter with a live chart preview and two reference sets pinned for
comparison](docs/screenshots/editor.png)

## Features

- **Open anything** - JSON or YAML (`.json`, `.yaml`, `.yml`), including
  invalid or incomplete files; problems become navigable validation issues,
  never a refusal to open. A legacy BPX v0.x file offers a choice: an
  unsaved converted copy (clearly labelled as approximate) or the file
  exactly as it is on disk, read-only.
- **Explore** - a three-pane editor (object tree, parameter list, inspector)
  with search, schema metadata (units, descriptions), a quick-glance info
  popover and a persistent per-parameter Documentation section with
  LaTeX-rendered symbols.
- **Validate continuously** - every change is re-checked by the official
  validator and its messages are shown verbatim; a Diagnostics page groups
  issues and outstanding work by section, keeping *invalid* distinct from
  *unfinished*, and the navigation rail badges the counts.
- **Edit every parameter kind** - scalar, integer, text, boolean, enum,
  function, table, map and series, through dedicated editing cards with
  undo/redo (the last 100 steps); a parameter the schema doesn't describe
  gets a raw JSON card instead of being locked out. Tables and series plot
  a live chart preview as you edit, and grids accept CSV import and
  clipboard paste, each behind a preview.
- **Author** - scaffold a new document for a chosen model (SPM, SPMe, DFN or
  Partial - the list comes from the schema itself), see which fields the
  schema still expects, and add custom parameters and sections where the
  schema allows them. The app never writes placeholder values for you.
- **Compare** - pin up to four read-only reference documents, from your own
  files or from the bundled library of PyBaMM-derived parameter sets
  (Chen2020, Prada2013, Ai2020, Mohtat2020). Differences are marked where
  you are already looking, and a single click copies a reference's value
  across as one undo step.
- **Chart validation runs** - an experiment card's Compare dialog overlays a
  Validation run's voltage, current and temperature traces against the
  document's other runs, the bundled About:Energy sample cells, or any
  other BPX file.
- **Read the raw file** - a Source view of the document's own JSON, foldable
  from the page header and, with a reference pinned, shown as two aligned
  panes with one-click pull chips on differing values.
- **Keep your work together** - a workspace is the main document plus the
  references pinned beside it. It is remembered as you go, reopens at
  launch, and can be named to keep it for good; if a file has moved since,
  the workspace reopens partially and says which file is missing instead of
  refusing.
- **Save and export** - write back to the source file, or export a copy as
  JSON or YAML. Saving is guarded: the app warns before dropping YAML
  comments and blocks a blind overwrite if the file changed on disk.

## A quick tour

![The Workspace board: the main document beside two pinned references with
difference counts, and the document's description, citation and file
record](docs/screenshots/workspace.png)

![The Source view with a reference pinned: two aligned panes, differing
values highlighted, and pull chips to copy a value across](docs/screenshots/source.png)

*Unfinished* and *invalid* are different things, and the Diagnostics page
keeps them apart. A freshly scaffolded document is all outstanding work and
no errors — and the checker says how far it could look:

![Diagnostics for a new SPM document: 23 outstanding required fields
grouped by section, zero errors, and a note that checking stopped at
Parameterisation](docs/screenshots/diagnostics_new.png)

An invalid file shows the official validator's verdict, verbatim, next to
the sections that are clean:

![Diagnostics for an invalid document: one model-level validator error
under State, shown word-for-word, with six sections
clear](docs/screenshots/diagnostics_invalid.png)

## Quick start

Requires **Python 3.12+**.

With [uv](https://docs.astral.sh/uv/) (recommended, installs the exact
locked dependencies):

```bash
uv sync
uv run python app/main_qt.py
```

With pip:

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -r app/requirements.txt
python app/main_qt.py
```

Then open your own BPX file (the Open button, drag-and-drop, or the
standard Open shortcut - ⌘O / Ctrl+O), dock a set from the reference
library, or start a new document for a chosen model from the Workspace
board.

## Bundled data

The app ships read-only data under `app/data/`, each set with its own
`NOTICE.md`:

- `example_documents/pybamm/` - the reference library: BPX conversions of
  four of PyBaMM's published lithium-ion parameter sets (Chen2020,
  Prada2013, Ai2020, Mohtat2020), BSD-3-Clause, regenerated offline by
  `scripts/generate_reference_library.py`.
- `example_documents/about_energy/` - the sample cells behind the
  validation-run charts: real NMC pouch and LFP 18650 parameterisations
  from About:Energy's public repository, CC BY-SA 4.0, rebuilt by
  `scripts/build_example_library.py`.
- `parameter_descriptions.yaml` - the per-parameter Documentation text.

## Design

A fuller design record, restored from the project's history, lives in
[docs/design/](docs/design/). A few principles shape the whole app:

- **The raw document is the source of truth.** The editable state is the raw
  BPX dictionary, so invalid and partially edited documents remain fully
  representable. The parsed model, the object tree and all validation issues
  are derived from it.
- **Validation belongs to `bpx`.** ExploreBPX owns presentation only.
  Validation semantics and messages come from the official package and are
  surfaced faithfully, never modified or "corrected" - if `bpx` says it
  twice, it is shown twice. Validation runs with `bpx`'s defaults, including
  its voltage tolerance `v_tol` (0.001 V), the slack `bpx` allows when
  checking a document's declared voltage limits against its electrode
  potentials. The gateway (`app/core/bpx_gateway.py:validate`) takes `v_tol`
  as a parameter; the UI does not yet expose it.
- **Completion is distinct from validation.** Validation answers whether the
  data satisfies BPX rules; completion answers whether a document is finished.
  A work-in-progress document is not the same thing as an incorrect one.
- **Never invent scientific values.** The app never writes placeholder values
  to make a document look complete or valid; exported BPX contains only data
  the user is prepared to claim.
- **The unit of work is a workspace** - one editable main document plus up to
  four read-only references, remembered between launches.

### Architecture

Strict one-way layering keeps all business logic independent of the frontend
- every arrow points inward, and nothing inward ever imports outward:

```text
ui_qt  →  state  →  core  →  bpx
```

| Layer | Responsibility |
|---|---|
| `app/ui_qt/` | PySide6 frontend: renders state, collects input, coordinates navigation. |
| `app/state/` | Frontend-agnostic session state: active document, selection, undo, workspaces. |
| `app/core/` | BPX integration, document model, validation, editing primitives, commands. |
| `bpx` | The official BPX package, pinned as a dependency (`bpx==1.1.1`). |

`core/` and `state/` never import a UI framework, and within the app
`core/bpx_gateway.py` is the only module that imports `bpx`. (Outside the
app, the dev-time library generator and a handful of contract tests import
`bpx` directly, on purpose - to pin the app against the real package.) The
UI is driven by the schema metadata `bpx` publishes, so new parameters in
future BPX versions appear automatically. A boundary test
(`tests/test_boundaries.py`) enforces the layering.

Every mutation travels one command spine (`core/commands.py` →
`core/command_service.py` → `core/editing.py`), so all edits - value changes
included - are previewed, guarded and undoable in exactly the same way.

```text
app/            the application: core / state / ui_qt
app/data/       bundled reference sets, sample cells and parameter docs
tests/          headless test suite
scripts/        offline dev tools that rebuild the bundled libraries
docs/           design records and README screenshots
```

## Testing

```bash
uv run pytest            # or, with the venv active: python -m pytest
```

The suite runs headless (offscreen Qt) and includes the boundary test that
keeps `core/` and `state/` free of UI imports. The README screenshots are
regenerated from the live app by `tests/readme_shots.py` (see its docstring),
so the images can't drift from what the app actually does.

## Linting

Code style follows the official `bpx` package's ruff configuration, adapted
for a Qt desktop app (see the carve-outs and their reasons in
`pyproject.toml`). Both commands must come back clean:

```bash
uv run ruff check app tests scripts
uv run ruff format --check app tests scripts
```

## Trust boundary

ExploreBPX is a local desktop app: it makes no network requests and reads
only the files you open (plus its own bundled reference library and saved
workspace state). Opened documents are parsed as data by the official `bpx`
package; nothing in a document runs as code, with one deliberate exception:
to draw chart previews, function-expression parameters are compiled to
Python callables by `bpx.Function`, whose grammar admits only numeric
expressions over `x` (arithmetic operators and a fixed set of maths
functions) — arbitrary identifiers and statements are rejected before
anything is built. Malformed or hostile files surface as validation issues,
not execution.

## License

BSD 3-Clause (see [LICENSE](LICENSE)). The bundled example parameter sets
carry their own licenses and attributions - see the `NOTICE.md` files under
`app/data/example_documents/`.
