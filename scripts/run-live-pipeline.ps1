# Live production workflow (Phase 1-6). Requires .env with production eBay credentials.
param(
    [string]$Query = "magic the gathering",
    [int]$MaxPages = 0,
    [switch]$SkipPrep,
    [switch]$SkipPhase1
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
. ./scripts/clear-ebay-env-overrides.ps1

$cli = Join-Path (Get-Location) ".venv\Scripts\ebay-workflows.exe"

& $cli validate-env
& $cli ebay-auth-check

if (-not $SkipPrep) {
    & $cli ensure-db-indexes
    & $cli sync-scryfall
    $faissPath = Join-Path (Get-Location) ".cache\faiss\index.bin"
    if (-not (Test-Path $faissPath)) {
        Write-Host "FAISS index missing — run build-faiss-index or use run-large-ingest.ps1 for full prep."
    }
}

$pageArg = @()
if ($MaxPages -gt 0) {
    $pageArg = @("--max-pages", $MaxPages)
}

if (-not $SkipPhase1) {
    & $cli run --query $Query --no-dry-run @pageArg --download-images
    & $cli retry-failed-images
}

& $cli phase2-match-title --top-k 3
& $cli sync-cardmarket
& $cli phase5-verify-ocr --use-real-ocr --use-embedding-match
& $cli phase3-join-prices
& $cli phase6-detect-lots --use-real-detection
& $cli phase4-rank --hybrid
New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null
& $cli export-rankings -o ./data/exports/ranked-live.json
& $cli data-integrity-check

Write-Host "Live pipeline completed."
