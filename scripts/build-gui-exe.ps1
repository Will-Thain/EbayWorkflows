# Build a standalone Windows GUI executable with PyInstaller (optional GUI-7 deliverable).
# Requires: pip install pyinstaller  (not part of default project deps)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "Installing PyInstaller into current environment..."
    python -m pip install pyinstaller
}

if (-not (python -c "import PySide6" 2>$null)) {
    Write-Host "Installing GUI extra (pyside6)..."
    python -m pip install -e ".[gui]"
}

$DistDir = Join-Path $RepoRoot "dist"
$BuildDir = Join-Path $RepoRoot "build\pyinstaller-gui"
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Write-Host "Building EbayWorkflows GUI executable (one-folder bundle)..."
pyinstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name EbayWorkflows `
    --distpath $DistDir `
    --workpath $BuildDir `
    --collect-all PySide6 `
    --hidden-import ebay_workflows.gui.qt_app `
    --paths (Join-Path $RepoRoot "src") `
    (Join-Path $RepoRoot "src\ebay_workflows\gui\qt_app.py")

Write-Host ""
Write-Host "Done. Run:"
Write-Host "  $DistDir\EbayWorkflows\EbayWorkflows.exe"
Write-Host ""
Write-Host "Place .env in the working directory when launching, or set DATABASE_URL in the environment."
