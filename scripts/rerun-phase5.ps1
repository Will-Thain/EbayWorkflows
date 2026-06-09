# Re-run Phase 5 after faiss_proposal fix, then phase 3, 4, and validation.
Set-Location $PSScriptRoot/..
$ErrorActionPreference = "Continue"

. ./scripts/activate-dev.ps1

$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
$log = "./data/exports/phase5-rerun.log"
New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null

$env:TORCH_DEVICE = "cpu"
$env:PYTHONUNBUFFERED = "1"
$env:PHASE5_SKIP_ANALYZED_IMAGES = "false"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $line
    Add-Content -Path $log -Value $line
}

function Invoke-PhaseCli {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CliArgs)
    $output = & $py -m ebay_workflows.cli @CliArgs 2>&1
    foreach ($line in $output) {
        Log ([string]$line)
    }
    return $LASTEXITCODE
}

Log "Clearing stale workflow steps (if any)"
$null = Invoke-PhaseCli clear-stale-workflows --yes

Log "Starting phase5-verify-ocr (real OCR + embedding match)"
$code = Invoke-PhaseCli phase5-verify-ocr --use-real-ocr --use-embedding-match
if ($code -ne 0) { Log "Phase 5 failed with exit $code"; exit $code }

Log "Starting phase3-join-prices"
$code = Invoke-PhaseCli phase3-join-prices
if ($code -ne 0) { Log "Phase 3 failed with exit $code"; exit $code }

Log "Starting phase4-rank --hybrid"
$code = Invoke-PhaseCli phase4-rank --hybrid
if ($code -ne 0) { Log "Phase 4 failed with exit $code"; exit $code }

Log "Running post-reanalyze-validation.ps1"
& ./scripts/post-reanalyze-validation.ps1 2>&1 | ForEach-Object { Log ([string]$_) }
Log "Phase 5 re-run pipeline completed."
