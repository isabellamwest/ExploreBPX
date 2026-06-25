# Explore_BPX

A lightweight application that makes [BPX](https://github.com/FaradayInstitution/BPX)
(Battery Parameter eXchange) files easier to create, open, understand, validate and
share — for both experimentalists and modellers. 

BPX files are designed to be machine-readable, but they can be difficult to inspect and navigate by hand, especially as they grow in size and complexity. Explore_BPX connects parameter *sources* to *simulators*, supports easier create/edit/visualise workflows, and validates beyond syntax.

The project builds on the official bpx package and provides a graphical interface for working with BPX files without needing to manually inspect JSON or YAML.

Explore_BPX does not implement the BPX specification itself. Parsing, validation and schema definitions are provided entirely by the official bpx package.

The long-term vision is a **standalone, dashboard-like application at the heart
of the BPX ecosystem** that simplifies BPX usage and increases adoption.

**Version 1 is a read-only foundation** — a small, well-layered
explorer that later versions extend without rewriting ([docs/roadmap.md](docs/roadmap.md) and [docs/architecture.md](docs/architecture.md)).

## Status — Version 1 (read-only explorer)

V1 is intentionally small but useful at every stage:

- **Open** JSON or YAML BPX files — including invalid ones, so you can see what
  is wrong.
- **Navigate** the structure: Tree → object's parameter list → parameter detail.
- **Inspect** a parameter in its own detail view with value, unit, schema
  description and full validation, typed by kind (scalar, integer, enum,
  function, table, unknown); a clickable breadcrumb navigates back up.
- **Validate** continuously: a marker flags affected parameters in the list, the
  full message shows in the parameter detail, and a Validation tab links straight
  to the offending parameter.
- **Export** the file as JSON or YAML (a faithful round-trip and format
  converter).

Editing, visualisation and file comparison are deliberately deferred — see
[docs/roadmap.md](docs/roadmap.md).

## Quick start

```powershell
# from the repository root, with a virtual environment activated
pip install -r app/requirements.txt
streamlit run app/main.py
```

Then open a file from [examples/](examples/) — `spm_example_valid.json` is a
valid file; the two A:E example files are older-format and load as *invalid*,
which is a good demonstration of exploring a broken file.

## Project structure

```
app/
  main.py            Streamlit entry point — wiring only, no logic
  core/              Frontend-agnostic business logic (never imports Streamlit)
    bpx_gateway.py   The only module that imports `bpx` (anti-corruption layer)
    document.py      BPXDocument — the raw dict is the source of truth
    tree_model.py    Builds the UI-neutral BPX object tree and parameter rows
    parameter_types.py  Classifies parameters by kind
    validation.py    Normalises BPX/Pydantic errors into ValidationIssues
    export.py        Serialises back to JSON/YAML
  state/
    app_state.py     AppState — current document + selection (no UI code)
  ui/                Streamlit panels — render and collect input only
examples/            Sample BPX files
tests/               Headless tests (run without Streamlit)
docs/                Architecture and roadmap
```

## Architecture

Strict layering — `ui → state → core → bpx` — so the frontend (Streamlit today,
potentially PySide6 later) can be replaced without touching business logic. See
[docs/architecture.md](docs/architecture.md) for the design decisions.

## BPX dependency

The `bpx` package is pinned exactly (`bpx==1.1.0`) and all coupling to it lives
in [app/core/bpx_gateway.py](app/core/bpx_gateway.py). The UI is driven by BPX's
own schema metadata, so new parameters in future BPX versions appear
automatically.

## Testing

```powershell
pip install pytest
python -m pytest
```

The suite runs entirely headless (no Streamlit required) and includes a boundary
test asserting that `core/` and `state/` never import a UI framework.
