# Launch PySide6 GUI without relying on ebay-workflows-gui.exe on PATH.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

python -m ebay_workflows.gui.qt_app
