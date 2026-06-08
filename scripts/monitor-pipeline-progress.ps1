# Read-only pipeline progress monitor (poll while reanalyze or long jobs run).
param(
    [int]$IntervalSeconds = 30,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Python venv not found at $python"
}

function Show-Progress {
    & $python -m ebay_workflows.cli monitor-pipeline
}

Show-Progress
if ($Once) { exit 0 }

Write-Host "Polling every $IntervalSeconds s (Ctrl+C to stop)..." -ForegroundColor DarkGray
while ($true) {
    Start-Sleep -Seconds $IntervalSeconds
    Write-Host ""
    Write-Host ("[{0}]" -f (Get-Date -Format "HH:mm:ss")) -ForegroundColor Cyan
    Show-Progress
}
