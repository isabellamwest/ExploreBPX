#!/usr/bin/env bash
# run.sh - one-step setup and launch for Explore_BPX on macOS / Linux.
#
# It will: verify Python >= 3.10, create a .venv if missing, activate it,
# upgrade pip, install app/requirements.txt, then launch the Streamlit app.
#
# Usage (from the repository root):
#   ./run.sh

set -euo pipefail

# Always operate from the repository root (the folder this script lives in).
cd "$(dirname "$0")"

# --- 1. Pick a Python interpreter (prefer python3) -------------------------
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Error: Python was not found. Install Python 3.10+ (e.g. 'brew install python@3.12')." >&2
    exit 1
fi

# --- 2. Verify Python 3.10+ ------------------------------------------------
if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Error: Python 3.10+ is required (bpx==1.1.0 does not support older versions)." >&2
    echo "Found: $("$PYTHON" --version 2>&1)" >&2
    exit 1
fi
echo "Using $("$PYTHON" --version 2>&1)"

# --- 3. Create the virtual environment if it does not exist ----------------
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv ..."
    "$PYTHON" -m venv .venv
fi

# --- 4. Activate it ---------------------------------------------------------
# shellcheck disable=SC1091
source .venv/bin/activate

# --- 5. Install dependencies ------------------------------------------------
python -m pip install --upgrade pip
pip install -r app/requirements.txt

# --- 6. Launch the app ------------------------------------------------------
streamlit run app/main.py
