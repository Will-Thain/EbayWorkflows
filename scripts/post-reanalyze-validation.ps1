# Run after reanalyze-matching.ps1 completes — sanity-check pipeline output.
Set-Location $PSScriptRoot/..

. ./scripts/activate-dev.ps1
$ErrorActionPreference = "Stop"

$cli = Join-Path (Get-Location) ".venv\Scripts\ebay-workflows.exe"
if (-not (Test-Path $cli)) {
    $py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
    function Invoke-Cli { param([string[]]$CliArgs) & $py -m ebay_workflows.cli @CliArgs }
} else {
    function Invoke-Cli { param([string[]]$CliArgs) & $cli @CliArgs }
}

$exportPath = "./data/exports/ranked-validation.json"
New-Item -ItemType Directory -Force -Path ./data/exports | Out-Null

Write-Host "=== Pipeline progress ==="
Invoke-Cli monitor-pipeline

Write-Host "`n=== Match statistics ==="
Invoke-Cli match-stats

Write-Host "`n=== Export rankings ==="
Invoke-Cli export-rankings -o $exportPath

Write-Host "`n=== Data integrity ==="
Invoke-Cli data-integrity-check

Write-Host "`nValidation complete. Export: $exportPath"
