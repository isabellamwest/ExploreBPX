# run.ps1 - one-step setup and launch for Explore_BPX on Windows (PowerShell).
#
# It will: verify Python >= 3.10, create a .venv if missing, activate it,
# upgrade pip, install app/requirements.txt, then launch the Streamlit app.
#
# Usage (from the repository root):
#   .\run.ps1
#
# If you get an execution-policy error, run this once in the same window:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

$ErrorActionPreference = "Stop"

# Always operate from the repository root (the folder this script lives in).
Set-Location -Path $PSScriptRoot

# --- 1. Verify Python 3.10+ is available -----------------------------------
$python = "python"
try {
    $versionLine = & $python --version 2>&1
} catch {
    Write-Error "Python was not found on your PATH. Install Python 3.10+ from https://www.python.org/downloads/ and reopen your terminal."
    exit 1
}

if ($versionLine -notmatch "(\d+)\.(\d+)") {
    Write-Error "Could not determine the Python version from '$versionLine'."
    exit 1
}
$major = [int]$Matches[1]
$minor = [int]$Matches[2]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Write-Error "Python 3.10+ is required (bpx==1.1.0 does not support older versions). Found $versionLine. Install a newer Python and try again."
    exit 1
}
Write-Host "Using $versionLine"

# --- 2. Create the virtual environment if it does not exist ----------------
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment in .venv ..."
    & $python -m venv .venv
}

# --- 3. Activate it ---------------------------------------------------------
& ".venv\Scripts\Activate.ps1"

# --- 4. Install dependencies ------------------------------------------------
python -m pip install --upgrade pip
pip install -r app/requirements.txt

# --- 5. Launch the app ------------------------------------------------------
streamlit run app/main.py
