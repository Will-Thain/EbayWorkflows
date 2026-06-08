# Remove stale match/score artifacts before re-running matching with new logic.
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
$ErrorActionPreference = "Continue"

$cli = Join-Path (Get-Location) ".venv\Scripts\ebay-workflows.exe"

& $cli clear-match-data --yes
