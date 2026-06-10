# Iterative smoke pipeline — small samples first, scale up when green.
# Tiers: 0=unit+single listing, 1=10 listings/30 images, 2=50/200, 3=full corpus.
param(
    [ValidateSet("0", "1", "2", "3")]
    [string]$Tier = "1",
    [switch]$SkipUnitTests,
    [switch]$SkipIngest,
    [switch]$ClearMatchData,
    [string]$ListingId = "6ea4f4d3",
    [int]$ListingMaxImages = 2,
    [string]$Query = "magic the gathering"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1

$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
$cli = Join-Path (Get-Location) ".venv\Scripts\ebay-workflows.exe"

if (-not (Test-Path $py)) {
    Write-Error "Missing .venv. Run: .\scripts\install-dev.ps1"
}

$tierConfig = @{
    "0" = @{ MaxPages = 0; MaxListings = 0; MaxImages = 0; RunPipeline = $false }
    "1" = @{ MaxPages = 1; MaxListings = 10; MaxImages = 30; RunPipeline = $true }
    "2" = @{ MaxPages = 3; MaxListings = 50; MaxImages = 200; RunPipeline = $true }
    "3" = @{ MaxPages = 0; MaxListings = 0; MaxImages = 0; RunPipeline = $true }
}

$cfg = $tierConfig[$Tier]
Write-Host "=== Smoke tier $Tier ===" -ForegroundColor Cyan
Write-Host "  max-pages=$($cfg.MaxPages) max-listings=$($cfg.MaxListings) max-images=$($cfg.MaxImages)"

function Invoke-Cli {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CliArgs)
    & $cli @CliArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not $SkipUnitTests) {
    Write-Host "`n=== Unit tests (EbayWorkflows) ==="
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $mtgRoot = Join-Path (Split-Path (Get-Location) -Parent) "mtg-card-recognition"
    if (Test-Path $mtgRoot) {
        Write-Host "`n=== Unit tests (mtg-card-recognition) ==="
        Push-Location $mtgRoot
        & $py -m pytest -q
        $mtgExit = $LASTEXITCODE
        Pop-Location
        if ($mtgExit -ne 0) { exit $mtgExit }
    }
}

if ($Tier -eq "0") {
    Write-Host "`n=== Single-listing Phase 5 validation ==="
    & $py scripts/validate_phase5_listing.py $ListingId --max-images $ListingMaxImages --use-embedding
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "`nTier 0 complete."
    exit 0
}

$sampleArgs = @()
if ($cfg.MaxListings -gt 0) { $sampleArgs += @("--max-listings", $cfg.MaxListings) }
if ($cfg.MaxImages -gt 0) { $sampleArgs += @("--max-images", $cfg.MaxImages) }

if ($ClearMatchData) {
    Write-Host "`n=== Clear match artifacts (keep listings/images) ==="
    Invoke-Cli clear-match-data --yes
}

Write-Host "`n=== Environment check ==="
Invoke-Cli validate-env

if (-not $SkipIngest -and $cfg.MaxPages -gt 0) {
    Write-Host "`n=== Phase 1 ingest (limited pages) ==="
    Invoke-Cli run --query $Query --no-dry-run --max-pages $cfg.MaxPages --download-images
}

Write-Host "`n=== Phases 2 -> 5 -> 3 -> 6 -> 4 (sample scope) ==="
Invoke-Cli phase2-match-title --top-k 3 @sampleArgs
Invoke-Cli phase5-verify-ocr --use-real-ocr --use-embedding-match @sampleArgs
Invoke-Cli phase3-join-prices
Invoke-Cli phase6-detect-lots --use-real-lot-detection @sampleArgs
Invoke-Cli phase4-rank --hybrid

Write-Host "`n=== Post-run validation ==="
& (Join-Path $PSScriptRoot "post-reanalyze-validation.ps1")

Write-Host "`nSmoke tier $Tier complete. Scale up with: .\scripts\run-smoke-pipeline.ps1 -Tier $($([int]$Tier + 1))"
