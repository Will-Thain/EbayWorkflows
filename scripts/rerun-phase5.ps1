# Re-run Phase 5 after faiss_proposal fix, then phase 3, 4, and validation.
Set-Location $PSScriptRoot/..
$ErrorActionPreference = "Stop"

. ./scripts/activate-dev.ps1

$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
$log = Join-Path (Get-Location) "data\exports\phase5-rerun.log"
$outLog = Join-Path (Get-Location) "data\exports\phase5-rerun-out.log"
$errLog = Join-Path (Get-Location) "data\exports\phase5-rerun-err.log"
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
    Remove-Item $outLog, $errLog -ErrorAction SilentlyContinue
    $proc = Start-Process -FilePath $py `
        -ArgumentList (@("-m", "ebay_workflows.cli") + $CliArgs) `
        -WorkingDirectory (Get-Location) `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru -Wait -NoNewWindow
    if (Test-Path $outLog) { Get-Content $outLog | ForEach-Object { Log $_ } }
    if (Test-Path $errLog) {
        $err = Get-Content $errLog -Raw
        if ($err) { Get-Content $errLog | ForEach-Object { Log $_ } }
    }
    return $proc.ExitCode
}

Log "Clearing stale workflow steps (if any)"
$null = Invoke-PhaseCli @("clear-stale-workflows", "--yes")

Log "Starting phase5-verify-ocr (real OCR + embedding match)"
$code = Invoke-PhaseCli @("phase5-verify-ocr", "--use-real-ocr", "--use-embedding-match")
if ($code -ne 0) { Log "Phase 5 failed with exit $code"; exit $code }

Log "Starting phase3-join-prices"
$code = Invoke-PhaseCli @("phase3-join-prices")
if ($code -ne 0) { Log "Phase 3 failed with exit $code"; exit $code }

Log "Starting phase4-rank --hybrid"
$code = Invoke-PhaseCli @("phase4-rank", "--hybrid")
if ($code -ne 0) { Log "Phase 4 failed with exit $code"; exit $code }

Log "Running post-reanalyze-validation.ps1"
& ./scripts/post-reanalyze-validation.ps1 2>&1 | ForEach-Object { Log ([string]$_) }
Log "Phase 5 re-run pipeline completed."
