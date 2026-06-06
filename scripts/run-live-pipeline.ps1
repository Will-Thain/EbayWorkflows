# Live production workflow (Phase 1-6). Requires .env with production eBay credentials.
param(
    [string]$Query = "magic the gathering",
    [int]$MaxPages = 1,
    [switch]$SkipPhase1
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
. ./scripts/clear-ebay-env-overrides.ps1

$cli = Join-Path (Get-Location) ".venv\Scripts\ebay-workflows.exe"

& $cli validate-env
& $cli ebay-auth-check

if (-not $SkipPhase1) {
    & $cli run --query $Query --no-dry-run --max-pages $MaxPages --download-images
}

& $cli phase2-match-title --top-k 3
& $cli sync-cardmarket
& $cli phase3-join-prices
& $cli phase5-verify-ocr --use-real-ocr --use-embedding-match
& $cli phase6-detect-lots --use-real-detection
& $cli phase4-rank --hybrid
New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null
& $cli export-rankings -o ./data/exports/ranked-live.json
& $cli data-integrity-check

Write-Host "Live pipeline completed."
