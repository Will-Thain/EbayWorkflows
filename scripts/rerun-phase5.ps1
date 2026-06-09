# Re-run Phase 5 after faiss_proposal fix, then phase 3, 4, and validation.
Set-Location $PSScriptRoot/..
$ErrorActionPreference = "Stop"

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

Log "Starting phase5-verify-ocr (real OCR + embedding match)"
& $py -m ebay_workflows.cli phase5-verify-ocr --use-real-ocr --use-embedding-match 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) { Log "Phase 5 failed with exit $LASTEXITCODE"; exit $LASTEXITCODE }

Log "Starting phase3-join-prices"
& $py -m ebay_workflows.cli phase3-join-prices 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) { Log "Phase 3 failed with exit $LASTEXITCODE"; exit $LASTEXITCODE }

Log "Starting phase4-rank --hybrid"
& $py -m ebay_workflows.cli phase4-rank --hybrid 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) { Log "Phase 4 failed with exit $LASTEXITCODE"; exit $LASTEXITCODE }

Log "Running post-reanalyze-validation.ps1"
& ./scripts/post-reanalyze-validation.ps1 2>&1 | ForEach-Object { Log $_ }
Log "Phase 5 re-run pipeline completed."
