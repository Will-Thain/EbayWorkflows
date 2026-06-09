# Install sibling mtg-card-recognition (editable) then EbayWorkflows.
# Run from repo root: .\scripts\install-dev.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Recognition = Join-Path (Split-Path -Parent $Root) "mtg-card-recognition"

if (-not (Test-Path (Join-Path $Recognition "pyproject.toml"))) {
    Write-Error "Expected clone at $Recognition - run: git clone https://github.com/Will-Thain/mtg-card-recognition.git"
}

$pip = Join-Path $Root ".venv\Scripts\pip.exe"
if (-not (Test-Path $pip)) {
    Write-Error "Create venv first: python -m venv .venv"
}

& $pip install -e $Recognition
Push-Location $Root
try {
    & $pip install -e ".[dev]"
} finally {
    Pop-Location
}
Write-Host "Done. mtg-card-recognition (editable) + ebay-workflows (editable)."
