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

$cli = Join-Path (Get-Location) ".venv\Scripts\ebay-workflows.exe"

Write-Host "Re-analyzing matches (Phase 2-6 + rank) with skip flags disabled..."

& $cli clear-match-data --yes
& $cli validate-env
& $cli phase2-match-title --top-k 3

if (-not (Test-Path "./.cache/images/set_symbol_templates/*.png")) {
    Write-Host "Building set symbol templates (first run)..."
    & $cli build-set-symbol-templates
}

& $cli phase5-verify-ocr --use-real-ocr --use-embedding-match
& $cli phase3-join-prices
if (-not $SkipPhase6) {
    & $cli phase6-detect-lots --use-real-detection
}
& $cli phase4-rank --hybrid
New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null
& $cli export-rankings -o ./data/exports/ranked-large-ingest.json
& $cli data-integrity-check

Write-Host "Re-analyze matching completed."
