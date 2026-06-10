# Re-run OCR/FAISS/lot detection and ranking after new images are cached.
# Does not clear existing title matches or re-ingest eBay listings.
# Order: Phase 5 (verify) -> Phase 3 (price join) -> Phase 6 -> Phase 4
# Rebuild FAISS after enabling FAISS_INDEX_USE_ART_ZONE: ebay-workflows build-faiss-index
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
$ErrorActionPreference = "Continue"

$env:PHASE5_SKIP_ANALYZED_IMAGES = "false"
$env:PHASE6_SKIP_ANALYZED_IMAGES = "false"

$cli = Join-Path (Get-Location) ".venv\Scripts\ebay-workflows.exe"

Write-Host "Refreshing Cardmarket bulk prices..."
& $cli download-cardmarket-bulk -o ./data/cardmarket/prices.csv
& $cli sync-cardmarket

if (-not (Test-Path "./.cache/images/set_symbol_templates/*.png")) {
    Write-Host "Building set symbol templates (first run)..."
    & $cli build-set-symbol-templates
}

Write-Host "Re-running image matching on full cached image set..."
& $cli phase5-verify-ocr --use-real-ocr --use-embedding-match
& $cli phase3-join-prices
& $cli phase6-detect-lots --use-real-lot-detection
& $cli phase4-rank --hybrid

New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null
& $cli export-rankings -o ./data/exports/ranked-large-ingest.json
& $cli data-integrity-check

Write-Host "Image matching rerun completed."
