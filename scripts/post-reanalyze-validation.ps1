# Re-run matching/scoring with fresh title matches and full image re-analysis.
# Use after matching-logic changes without re-ingesting eBay listings.
# Order: Phase 2 -> Phase 5 -> Phase 3 -> Phase 6 -> Phase 4
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
$ErrorActionPreference = "Stop"

$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Missing .venv. Run: py -3.12 -m venv .venv; pip install -e '.[dev,gpu]'"
}

function Invoke-Cli {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CliArgs)
    & $py -m ebay_workflows.cli @CliArgs
}

$exportPath = "./data/exports/ranked-validation.json"
New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null

Write-Host "=== Pipeline progress ==="
Invoke-Cli monitor-pipeline

Write-Host "`n=== Match statistics ==="
Invoke-Cli match-stats

Write-Host "`n=== Export rankings ==="
Invoke-Cli export-rankings --output $exportPath

Write-Host "`n=== Data integrity ==="
Invoke-Cli data-integrity-check

Write-Host "`nValidation complete. Export: $exportPath"
