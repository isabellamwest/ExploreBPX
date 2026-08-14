# ExploreBPX

A desktop app that makes [BPX](https://github.com/FaradayInstitution/BPX)
(Battery Parameter eXchange) files easy to open, understand, validate, edit
and author.

BPX files are machine-readable JSON/YAML, but can be hard to inspect and navigate by
hand as they grow. ExploreBPX presents a BPX document as a navigable tree of
objects and parameters with continuous validation, a dedicated editor for
every parameter kind, and authoring support for building new documents from
model skeletons.

It builds on the official `bpx` package and deliberately implements none of
the BPX specification itself: parsing, schema and validation all come from
`bpx`, and the app's job is to surface them faithfully.

## Features

- **Open anything** - JSON or YAML, including invalid or incomplete files;
  problems become navigable validation issues, never a refusal to open.
- **Explore** - a three-pane editor (object tree, parameter list, inspector)
  with search, schema metadata (units, descriptions) and per-parameter
  documentation.
- **Validate continuously** - every change is re-checked by the official
  validator; a Diagnostics page groups issues and outstanding work by
  section, keeping *invalid* distinct from *unfinished*.
- **Edit every parameter kind** - scalar, integer, text, boolean, enum,
  function, table, map and series, through dedicated editing cards with
  full undo/redo; tables plot a live chart preview as you edit.
- **Author** - scaffold a new document for a chosen model (SPM, SPMe, DFN or
  Partial), see which fields the schema still expects, and add custom
  parameters and sections where the schema allows them.
- **Compare** - pin up to four read-only reference documents, from your own
  files or from the bundled library of PyBaMM-derived parameter sets
  (Chen2020, Prada2013, Ai2020, Mohtat2020). Differences are marked where you
  are already looking, and a single click copies a reference's value across as
  one undo step. Validation runs overlay against bundled example data as
  charts.
- **Read the raw file** - a Source view of the document's own JSON, foldable
  and, with a reference pinned, shown as two aligned panes.
- **Keep your work together** - a workspace is the main document plus the
  references pinned beside it. It is remembered as you go, reopens at launch,
  and can be named to keep it for good.
- **Save and export** - write back to the source file, or export a copy as
  JSON or YAML.

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

Then open your own BPX file, dock a set from the reference library, or start
a new document for a chosen model from the Workspace board.

## Design

A few principles shape the whole app:

- **The raw document is the source of truth.** The editable state is the raw
  BPX dictionary, so invalid and partially edited documents remain fully
  representable. The parsed model, the object tree and all validation issues
  are derived from it.
- **Validation belongs to `bpx`.** ExploreBPX owns presentation only.
  Validation semantics and messages come from the official package and are
  surfaced faithfully, never modified or "corrected".
- **Completion is distinct from validation.** Validation answers whether the
  data satisfies BPX rules; completion answers whether a document is finished.
  A work-in-progress document is not the same thing as an incorrect one.
- **Never invent scientific values.** The app never writes placeholder values
  to make a document look complete or valid; exported BPX contains only data
  the user is prepared to claim.
- **The unit of work is a workspace** - one editable main document plus up to
  four read-only references, remembered between launches.

### Architecture

Strict one-way layering keeps all business logic independent of the frontend:

```text
ui_qt  →  state  →  core  →  bpx
```

| Layer | Responsibility |
|---|---|
| `app/ui_qt/` | PySide6 frontend: renders state, collects input, coordinates navigation. |
| `app/state/` | Frontend-agnostic session state: active document, selection, undo, workspaces. |
| `app/core/` | BPX integration, document model, validation, editing primitives, commands. |
| `bpx` | The official BPX package, pinned as a dependency. |

`core/` and `state/` never import a UI framework, and
`core/bpx_gateway.py` is the only module in `app/` that imports `bpx` (pinned
`bpx==1.1.1`). The UI is driven by the schema metadata `bpx` publishes, so
new parameters in future BPX versions appear automatically. A boundary test
(`tests/test_boundaries.py`) enforces the layering.

Every mutation travels one command spine (`core/commands.py` →
`core/command_service.py` → `core/editing.py`), so all edits - value changes
included - are previewed, guarded and undoable in exactly the same way.

```text
app/        the application: core / state / ui_qt, plus bundled data
tests/      headless test suite
scripts/    offline dev tools (reference- and example-library generators)
```

## Testing

```bash
uv run pytest            # or, with the venv active: python -m pytest
```

The suite runs headless (offscreen Qt) and includes the boundary test that
keeps `core/` and `state/` free of UI imports.

## License

BSD 3-Clause (see [LICENSE](LICENSE)). The bundled example parameter sets
carry their own licenses and attributions - see the `NOTICE.md` files under
`app/data/example_documents/`.

## Linting

Code style follows the official `bpx` package's ruff configuration, adapted
for a Qt desktop app (see the carve-outs and their reasons in
`pyproject.toml`). Both commands must come back clean:

```bash
uv run ruff check app tests scripts
uv run ruff format --check app tests scripts
```
