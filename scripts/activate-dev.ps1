# Project dev environment: venv, Tesseract, PostgreSQL tools on PATH.
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$venvScripts = Join-Path $Root ".venv\Scripts"
if (-not (Test-Path (Join-Path $venvScripts "python.exe"))) {
    Write-Error "Missing .venv. Run: py -3.11 -m venv .venv; .\.venv\Scripts\pip install -e `".[dev,gpu]`""
}

$env:Path = @(
    $venvScripts,
    "C:\Program Files\Tesseract-OCR",
    "C:\Program Files\PostgreSQL\18\bin",
    $env:Path
) -join ";"

Write-Host "Dev environment ready (venv + Tesseract + psql on PATH)."
Write-Host "Try: ebay-workflows validate-env"
