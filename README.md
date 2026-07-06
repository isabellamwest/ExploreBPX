# Explore_BPX

A lightweight application that makes [BPX](https://github.com/FaradayInstitution/BPX)
(Battery Parameter eXchange) files easier to create, open, understand, validate and
share — for both experimentalists and modellers. 

BPX files are designed to be machine-readable, but they can be difficult to inspect and navigate by hand, especially as they grow in size and complexity. Explore_BPX connects parameter *sources* to *simulators*, supports easier create/edit/visualise workflows, and validates beyond syntax.

The project builds on the official bpx package and provides a graphical interface for working with BPX files without needing to manually inspect JSON or YAML.

Explore_BPX does not implement the BPX specification itself. Parsing, validation and schema definitions are provided entirely by the official bpx package.

The long-term vision is a **standalone, dashboard-like application at the centre
of the BPX ecosystem**, that simplifies BPX usage and increases adoption.

**Version 1 is the current PySide6 desktop application**: a BPX explorer with
continuous validation and the first editing foundation in place. Later versions
build on the same backend layers without restarting the app architecture
([docs/04-roadmap.md](docs/04-roadmap.md) and
[docs/01-architecture.md](docs/01-architecture.md)).

## Status — Version 1

V1 is intentionally small but useful: a desktop app for opening, inspecting,
validating and beginning to edit BPX files.

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
- **Edit** scalar, integer and enum values through the Qt editing cards, backed
  by command-based state and live validation.

Creation workflows, function/table editors, visualisation and comparison remain
ahead on the roadmap.

## Quick start

> **Requires Python 3.10 or newer.** The pinned `bpx==1.1.0` dependency does not
> support Python 3.9 or earlier. If you try to install on an older Python you
> will see a confusing error like
> `Could not find a version that satisfies the requirement bpx==1.1.0`.

### 1. Check your Python version first

Run this before anything else and confirm it prints `3.10` or higher:

```text
python --version
```

If your default `python` is older than 3.10 (or the command is missing):

- On **Windows**, install Python 3.10+ from [python.org](https://www.python.org/downloads/)
  (tick "Add python.exe to PATH" in the installer), then open a new terminal.
- On **macOS**, install a newer Python (e.g. `brew install python@3.12`) and use
  `python3` / `python3.12` in the commands below. You can check candidates with
  `python3 --version`.

### 2. Set up and run

The steps are the same on every OS — only the activate command differs. Run them
**from the repository root**.

**Windows (PowerShell)**

```powershell
python -m venv .venv               # create the virtual environment (once)
.venv\Scripts\Activate.ps1         # activate it
python -m pip install --upgrade pip
pip install -r app/requirements.txt
python app/main_qt.py
```

**macOS / Linux (zsh or bash)**

```bash
python3 -m venv .venv              # create the virtual environment (once)
source .venv/bin/activate          # activate it
python -m pip install --upgrade pip
pip install -r app/requirements.txt
python app/main_qt.py
```

The PySide6 desktop app is the Version 1 frontend. Further editing, creation and
visualisation workflows will be added here.

Then open a file from [examples/](examples/) — `spm_example_valid.json` is a
valid file; the two A:E example files are older-format and load as *invalid*,
which is a good demonstration of exploring a broken file.

### 3. Clean up (reclaim disk space)

The `.venv` folder can be large. When you are done, deactivate and delete it —
you can always recreate it later with the steps above.

**Windows (PowerShell)**

```powershell
deactivate                         # if the venv is still active
Remove-Item -Recurse -Force .venv
```

**macOS / Linux (zsh or bash)**

```bash
deactivate                         # if the venv is still active
rm -rf .venv
```

## Working on this project from any machine (laptop + desktop)

You can work on Explore_BPX from both your macOS laptop and your Windows desktop.
GitHub holds the single source of truth; each machine keeps its own local copy
that you sync with `git pull` (download changes) and `git push` (upload changes).

### 1. One-time setup on each machine

Clone the repo once per machine, then move into the project folder. The commands
are the same on both:

**Windows (PowerShell)**

```powershell
git clone https://github.com/isabellamwest/Explore_BPX.git
cd Explore_BPX
```

**macOS / Linux (zsh or bash)**

```bash
git clone https://github.com/isabellamwest/Explore_BPX.git
cd Explore_BPX
```

### 2. Run it

Use the venv setup from [Quick start](#quick-start), then launch from the
project root with `python app/main_qt.py`.

### 3. Everyday edit-and-commit loop (new to git? start here)

Whenever you sit down to work, follow this loop. The git commands are identical
on Windows and macOS — only the terminal differs (PowerShell vs zsh/bash).

**Step 1 — Always pull the latest first.** This pulls in anything you (or others)
pushed from the other machine, so you don't end up with conflicting copies:

```text
git pull
```

**Step 2 — Make your edits** in your editor and save.

**Step 3 — Stage and commit your changes.** `git add -A` stages everything you
changed; the commit records a snapshot with a short message describing it:

```text
git add -A
git commit -m "Describe what you changed"
```

**Step 4 — Push your work back to GitHub.** You have two options:

*Option A — commit straight to `main`* (simplest; fine when you're the only one
working on it):

```text
git push origin main
```

*Option B — put your work on a new branch and open a Pull Request* (safer; lets
you review changes before they land on `main`):

```text
git switch -c my-branch-name
git push -u origin my-branch-name
```

Then go to the repo on GitHub and click **Compare & pull request** to open a PR.

### 4. Keep both machines in sync

The golden rule: **`git pull` before you start, `git push` when you finish.** If
you always push from the machine you just worked on and always pull on the
machine you move to next, both copies stay up to date and you avoid conflicts.

## Project structure

```
app/
  main_qt.py         PySide6 entry point (Version 1 desktop app)
  core/              Frontend-agnostic business logic (never imports UI code)
    bpx_gateway.py   The only module that imports `bpx` (anti-corruption layer)
    document.py      BPXDocument — the raw dict is the source of truth
    editing.py       Low-level immutable raw-dict mutation primitives
    commands.py      Operation intents and result contracts
    command_service.py  Command orchestration (preview/execute)
    structure.py     Structural capability queries (required/removable sections)
    document_factory.py  Incomplete document scaffolds (SPM/SPMe/DFN/Partial)
    tree_model.py    Builds the UI-neutral BPX object tree and parameter rows
    parameter_types.py  Classifies parameters by kind
    validation.py    Normalises BPX/Pydantic errors into ValidationIssues
    export.py        Serialises back to JSON/YAML
  state/
    app_state.py     AppState — document session + selection + command undo
  ui_qt/             PySide6 desktop frontend
examples/            Sample BPX files
tests/               Headless tests
docs/                Architecture and roadmap
```

## Architecture

Strict layering — `frontend → state → core → bpx` — so the frontend can evolve
without touching business logic. See
[docs/01-architecture.md](docs/01-architecture.md) for the architecture and its
design rationale.

## BPX dependency

The `bpx` package is pinned exactly (`bpx==1.1.0`) and all coupling to it lives
in [app/core/bpx_gateway.py](app/core/bpx_gateway.py). The UI is driven by BPX's
own schema metadata, so new parameters in future BPX versions appear
automatically.

## Testing

With the virtual environment activated (see Quick start), run the headless suite
from the repository root. The commands are identical on every OS:

```text
pip install pytest
python -m pytest
```

The suite runs entirely headless and includes a boundary test asserting that
`core/` and `state/` never import a UI framework.
