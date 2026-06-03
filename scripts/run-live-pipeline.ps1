# Live production workflow (Phase 1-6). Requires .env with production eBay credentials.
param(
    [string]$Query = "magic the gathering",
    [int]$MaxPages = 1,
    [switch]$SkipPhase1
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

. ./scripts/clear-ebay-env-overrides.ps1
ebay-workflows validate-env
ebay-workflows ebay-auth-check

if (-not $SkipPhase1) {
    ebay-workflows run --query $Query --no-dry-run --max-pages $MaxPages --download-images
}

ebay-workflows phase2-match-title --top-k 3
ebay-workflows sync-cardmarket
ebay-workflows phase3-join-prices
ebay-workflows phase4-rank --hybrid
ebay-workflows phase5-verify-ocr --use-real-ocr --use-embedding-match
ebay-workflows phase6-detect-lots --use-real-detection
New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null
ebay-workflows export-rankings -o ./data/exports/ranked-live.json
ebay-workflows data-integrity-check

Write-Host "Live pipeline completed."
