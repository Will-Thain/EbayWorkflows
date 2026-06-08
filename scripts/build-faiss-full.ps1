# Append 10k-card FAISS batches until all Scryfall art is indexed.
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
$ErrorActionPreference = "Continue"

New-Item -ItemType Directory -Force -Path ./data | Out-Null
$log = "./data/faiss-build-full.log"

Write-Host "Batched full FAISS build (10k per batch, append mode)..."
Write-Host "Log: $log"

& .\.venv\Scripts\ebay-workflows.exe build-faiss-index-batches --batch-size 10000 *>&1 |
    Tee-Object -FilePath $log

$exitCode = $LASTEXITCODE
if ($null -eq $exitCode) { $exitCode = 0 }
if ($exitCode -ne 0) {
    Write-Error "build-faiss-index-batches exited with code $exitCode"
    exit $exitCode
}

Write-Host "Full FAISS index build finished."
