# Rebuild FAISS index (art-zone crops) then re-run full matching pipeline.
Set-Location $PSScriptRoot/..
$ErrorActionPreference = "Continue"

. ./scripts/activate-dev.ps1

$logDir = "./data/exports"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "faiss-rebuild-and-reanalyze.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $line
    Add-Content -Path $log -Value $line
}

Log "Starting art-zone FAISS full rebuild (FAISS_INDEX_USE_ART_ZONE=true)..."
& ./scripts/build-faiss-full.ps1 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
    Log "FAISS build failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Log "FAISS rebuild complete. Running validate-env..."
& .\.venv\Scripts\ebay-workflows.exe validate-env 2>&1 | ForEach-Object { Log $_ }

Log "Starting reanalyze-matching..."
& ./scripts/reanalyze-matching.ps1 2>&1 | ForEach-Object { Log $_ }
Log "Operational pipeline finished."
