# Explore_BPX

A desktop app that makes [BPX](https://github.com/FaradayInstitution/BPX)
(Battery Parameter eXchange) files easy to open, understand, validate, edit
and author.

BPX files are machine-readable JSON/YAML, but can be hard to inspect and navigate by
hand as they grow. Explore_BPX presents a BPX document as a navigable tree of
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
- **Compare** - dock a read-only reference document from a file or from the
  bundled library of PyBaMM-derived parameter sets (Chen2020, Prada2013,
  Ai2020, Mohtat2020), and compare validation runs against bundled example
  data in overlaid charts.
- **Save and export** - write back to the source file, or export a copy as
  JSON or YAML.

## Quick start

Requires **Python 3.12+**.

> **Clone outside a synced folder.** Don't put the checkout inside iCloud
> Drive, OneDrive or Dropbox. Those file providers set the macOS `hidden`
> flag (and the Windows equivalent) on dot-directories and everything beneath
> them, including `.venv`. Qt's plugin loader skips hidden directory entries,
> so the app dies at startup with *"Could not find the Qt platform plugin
> cocoa"* even though the plugin is present and loadable. A `.git` directory
> under a sync client is also a known source of repository corruption.

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

Then open your own BPX file, dock a set from the reference library, or use
**New** to scaffold a document for a chosen model.

## Architecture

Strict one-way layering - `ui_qt → state → core → bpx` - keeps all business
logic independent of the frontend. `core/bpx_gateway.py` is the only module
that imports `bpx` (pinned `bpx==1.1.1`), and the UI is driven by the schema
metadata `bpx` publishes, so new parameters in future BPX versions appear
automatically. A boundary test enforces the layering.

```text
app/        the application: core / state / ui_qt
docs/       design reference
tests/      headless test suite
scripts/    offline dev tools (reference-library generator)
```

See [docs/architecture.md](docs/architecture.md) for the full design —
principles, domain model, module map and UI shell — and
[docs/future.md](docs/future.md) for the ideas backlog.

## Testing

```bash
uv run pytest            # or, with the venv active: python -m pytest
```

The suite runs headless (offscreen Qt) and includes the boundary test that
keeps `core/` and `state/` free of UI imports.
