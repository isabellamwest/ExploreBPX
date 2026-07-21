# Explore_BPX

A lightweight application that makes [BPX](https://github.com/FaradayInstitution/BPX)
(Battery Parameter eXchange) files easier to create, open, understand, validate and
share — for both experimentalists and modellers. 

BPX files are designed to be machine-readable, but they can be difficult to inspect and navigate by hand, especially as they grow in size and complexity. Explore_BPX connects parameter *sources* to *simulators*, supports easier create/edit/visualise workflows, and validates beyond syntax.

The project builds on the official bpx package and provides a graphical interface
for working with BPX files without needing to manually inspect JSON or YAML. It
does not implement the BPX specification itself — parsing, validation and schema
definitions are provided entirely by the official `bpx` package.

## Status

Explore_BPX is a PySide6 desktop app: open, navigate, inspect and validate BPX
files continuously, edit every declared parameter kind (scalar, integer, enum,
text, boolean, function, table, map, series) through dedicated editing cards with
command-based undo/redo, author new documents from a model scaffold, add/remove/
rename structure, and export as JSON or YAML. See
[docs/05-future.md](docs/05-future.md) for speculative direction, or the active
`PLAN-*.md` at the repo root for in-flight work.

## Quick start

> **Requires Python 3.10 or newer.** The pinned `bpx==1.1.1` dependency does not
> support Python 3.9 or earlier. If you try to install on an older Python you
> will see a confusing error like
> `Could not find a version that satisfies the requirement bpx==1.1.1`.

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

Then open your own BPX file (JSON or YAML) to explore it, or use **New** on
the workspace page to start a fresh scaffold for a chosen model (SPM, SPMe,
DFN or Partial).

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

GitHub holds the single source of truth; each machine keeps its own local copy
synced with `git pull` / `git push`.

**One-time setup on each machine:**

```bash
git clone https://github.com/isabellamwest/Explore_BPX.git
cd Explore_BPX
```

Then set up the venv as in [Quick start](#quick-start) and run with
`python app/main_qt.py`.

**Everyday loop:**

1. `git pull` first, to bring in anything pushed from the other machine.
2. Make your edits.
3. `git add -A && git commit -m "Describe what you changed"`.
4. Push: `git push origin main` (simplest, solo work), or push a branch and open
   a PR (`git switch -c my-branch-name && git push -u origin my-branch-name`,
   then **Compare & pull request** on GitHub).

Golden rule: **pull before you start, push when you finish** — on whichever
machine you used last.

## Project structure

Strict layering — `frontend (ui_qt) → state → core → bpx` — so the frontend can
evolve without touching business logic; `core/` and `state/` never import a UI
framework, and `core/bpx_gateway.py` is the sole module that imports `bpx`. See
[docs/01-architecture.md](docs/01-architecture.md) for the module map and design
rationale.

## BPX dependency

The `bpx` package is pinned exactly (`bpx==1.1.1`) and all coupling to it lives
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
