# Explore_BPX

A lightweight application that makes [BPX](https://github.com/FaradayInstitution/BPX)
(Battery Parameter eXchange) files easier to open, understand, validate and
share — for both experimentalists and modellers.

Explore_BPX is **not** a BPX implementation. It consumes the official `bpx`
package for all parsing, validation and schema definitions, and focuses purely
on the question: *how do humans interact with BPX files?*

## Status — Version 1 (read-only explorer)

V1 is intentionally small but useful at every stage:

- **Open** JSON or YAML BPX files — including invalid ones, so you can see what
  is wrong.
- **Navigate** the structure: Tree → Section → Parameter → Inspector.
- **Inspect** every parameter with its value, unit and schema description, typed
  by kind (scalar, integer, enum, function, table, section).
- **Validate** continuously: errors and warnings appear inline on parameters and
  in a Validation tab that links straight to the offending parameter.
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
    tree_model.py    Builds the UI-neutral parameter tree
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

## Architecture in one line

Strict layering — `ui → state → core → bpx` — so the frontend (Streamlit today,
potentially PySide6 later) can be replaced without touching business logic. See
[docs/architecture.md](docs/architecture.md) for the design decisions and
trade-offs.

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
