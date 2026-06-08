# Build 10k-card FAISS index without PowerShell aborting on OpenCLIP stderr warnings.
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
$ErrorActionPreference = "Continue"

New-Item -ItemType Directory -Force -Path ./data | Out-Null
$log = "./data/faiss-build-10k.log"

Write-Host "Building FAISS index (max cards from FAISS_BUILD_MAX_CARDS / --max-cards)..."
Write-Host "Log: $log"

& .\.venv\Scripts\ebay-workflows.exe build-faiss-index --max-cards 10000 *>&1 |
    Tee-Object -FilePath $log

if ($LASTEXITCODE -ne 0) {
    Write-Error "build-faiss-index exited with code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "FAISS build completed."
