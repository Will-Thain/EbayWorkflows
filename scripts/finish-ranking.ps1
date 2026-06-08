# Finish pipeline after Phase 5/3 — rank, export, validate (skip Phase 6).
Set-Location $PSScriptRoot/..
$ErrorActionPreference = "Stop"

. ./scripts/activate-dev.ps1

$logDir = "./data/exports"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "finish-ranking.log"
$outLog = Join-Path $logDir "finish-out.log"
$errLog = Join-Path $logDir "finish-err.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $line
    Add-Content -Path $log -Value $line
}

$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Missing .venv. Run: py -3.11 -m venv .venv; pip install -e '.[dev,gpu]'"
}

$env:PYTHONUNBUFFERED = "1"
$env:TORCH_DEVICE = "cpu"
Remove-Item $outLog, $errLog -ErrorAction SilentlyContinue

Log "Running scripts/finish_ranking.py (minimal import path)"
$proc = Start-Process -FilePath $py `
    -ArgumentList (Join-Path (Get-Location) "scripts\finish_ranking.py") `
    -WorkingDirectory (Get-Location) `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru -Wait -NoNewWindow

if (Test-Path $outLog) { Get-Content $outLog | ForEach-Object { Log $_ } }
if (Test-Path $errLog) {
    $err = Get-Content $errLog -Raw
    if ($err) {
        Log "stderr:"
        Get-Content $errLog | ForEach-Object { Log $_ }
    }
}

if ($proc.ExitCode -ne 0) {
    Log "finish_ranking.py failed with exit code $($proc.ExitCode)"
    exit $proc.ExitCode
}

Log "Running post-reanalyze-validation.ps1"
& ./scripts/post-reanalyze-validation.ps1 2>&1 | ForEach-Object { Log $_ }
Log "Finish-ranking completed."
