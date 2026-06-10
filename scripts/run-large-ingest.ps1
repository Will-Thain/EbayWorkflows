# Large-scale eBay ingest - production prep + full pipeline.
# Requires .env with live eBay credentials and DISABLE_LIVE_API_WRITES=false.
param(
    [string]$Query = "magic the gathering mtg",
    [int]$MaxPages = 0,
    [string]$QueriesFile = "scripts/queries/mtg-default.txt",
    [switch]$SkipPrep,
    [switch]$SkipPhase1,
    [switch]$RefreshExisting,
    [switch]$RebuildFaiss,
    [switch]$ReanalyzeMatching
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
. ./scripts/clear-ebay-env-overrides.ps1

$cli = Join-Path (Get-Location) ".venv\Scripts\ebay-workflows.exe"

if ($RefreshExisting) {
    $env:PHASE1_SKIP_EXISTING_LISTINGS = "false"
}

& $cli validate-env
& $cli ebay-auth-check
& $cli init-db
& $cli ensure-db-indexes

if (-not $SkipPrep) {
    & $cli sync-scryfall
    $buildAll = ($env:FAISS_BUILD_ALL_CARDS -eq "true")
    if ($RebuildFaiss -or $buildAll) {
        if ($buildAll) {
            Write-Host "FAISS_BUILD_ALL_CARDS=true — running full batched index build (art-zone crops)..."
            & ./scripts/build-faiss-full.ps1
        } else {
            Write-Host "Rebuilding FAISS index (art-zone crops when FAISS_INDEX_USE_ART_ZONE=true)..."
            & $cli build-faiss-index
        }
    } else {
        $faissPath = Join-Path (Get-Location) ".cache\faiss\index.bin"
        if (-not (Test-Path $faissPath)) {
            Write-Host "FAISS index missing - building (FAISS_BUILD_MAX_CARDS from .env)..."
            & $cli build-faiss-index
        } else {
            Write-Host "FAISS index present at $faissPath - skipping build (use -RebuildFaiss to force)."
        }
    }
    $cmPath = Join-Path (Get-Location) "data\cardmarket\prices.csv"
    if (-not (Test-Path $cmPath)) {
        Write-Host "Cardmarket bulk CSV missing - downloading..."
        New-Item -ItemType Directory -Force -Path ./data/cardmarket | Out-Null
        & $cli download-cardmarket-bulk -o ./data/cardmarket/prices.csv
    }
    & $cli sync-cardmarket
}

$pageArg = @()
if ($MaxPages -gt 0) {
    $pageArg = @("--max-pages", $MaxPages)
}

$queryArg = @("--query", $Query)
if ($QueriesFile -and (Test-Path $QueriesFile)) {
    $queryArg += @("--queries-file", $QueriesFile)
}

if (-not $SkipPhase1) {
    & $cli run --no-dry-run @queryArg @pageArg --download-images
    & $cli retry-failed-images
}

if ($ReanalyzeMatching) {
    $env:PHASE2_SKIP_UNCHANGED_LISTINGS = "false"
    $env:PHASE5_SKIP_ANALYZED_IMAGES = "false"
    $env:PHASE6_SKIP_ANALYZED_IMAGES = "false"
}

& $cli phase2-match-title --top-k 3
& $cli phase5-verify-ocr --use-real-ocr --use-embedding-match
& $cli phase3-join-prices
& $cli phase6-detect-lots --use-real-lot-detection
& $cli phase4-rank --hybrid
New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null
& $cli export-rankings -o ./data/exports/ranked-large-ingest.json
& $cli data-integrity-check

Write-Host "Large-scale ingest pipeline completed."
