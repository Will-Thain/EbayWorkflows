# Re-run matching/scoring with fresh title matches and full image re-analysis.
# Use after matching-logic changes without re-ingesting eBay listings.
# Order: Phase 2 -> Phase 5 -> Phase 3 -> Phase 6 -> Phase 4
param(
    [switch]$SkipPhase6
)

Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
$ErrorActionPreference = "Continue"

$env:PHASE2_SKIP_UNCHANGED_LISTINGS = "false"
$env:PHASE5_SKIP_ANALYZED_IMAGES = "false"
$env:PHASE6_SKIP_ANALYZED_IMAGES = "false"

$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Missing .venv. Run: py -3.12 -m venv .venv; pip install -e '.[dev,gpu]'"
}

function Invoke-Cli {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CliArgs)
    & $py -m ebay_workflows.cli @CliArgs
}

Write-Host "Re-analyzing matches (Phase 2-5, 3, 4 + rank; Phase 6 optional) with skip flags disabled..."

Invoke-Cli clear-match-data -y
Invoke-Cli validate-env
Invoke-Cli phase2-match-title --top-k 3

if (-not (Test-Path "./.cache/images/set_symbol_templates/*.png")) {
    Write-Host "Building set symbol templates (first run)..."
    Invoke-Cli build-set-symbol-templates
}

Invoke-Cli phase5-verify-ocr --use-real-ocr --use-embedding-match
Invoke-Cli phase3-join-prices
if (-not $SkipPhase6) {
    Invoke-Cli phase6-detect-lots --use-real-detection
}
Invoke-Cli phase4-rank --hybrid
New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null
Invoke-Cli export-rankings -o ./data/exports/ranked-large-ingest.json
Invoke-Cli data-integrity-check

Write-Host "Re-analyze matching completed."
