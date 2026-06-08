# Launch PySide6 GUI without relying on ebay-workflows-gui.exe on PATH.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "py"
    $guiArgs = @("-m", "ebay_workflows.gui.qt_app")
    & $python @guiArgs
    exit $LASTEXITCODE
}

& $python -m ebay_workflows.gui.qt_app
