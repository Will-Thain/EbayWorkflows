#Requires -Version 5.1
<#
.SYNOPSIS
  Smoke validation for non-blocker backlog items (repos, metrics, import boundaries).
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "== pytest (quick) ==" -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m pytest -q tests/test_import_boundaries.py tests/test_repositories.py tests/test_tier7_metrics.py tests/test_labeled_crops_manifest.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== doc grep (stale layout in non-historical docs) ==" -ForegroundColor Cyan
$hits = rg "services/|workflow_phase" docs/ --glob "!**/expert-panel/**" --glob "!**/adr/**" 2>$null
if ($hits) {
    Write-Warning "Review stale doc references:`n$hits"
} else {
    Write-Host "No stale services/workflow_phase references outside expert/adr." -ForegroundColor Green
}

Write-Host "Done." -ForegroundColor Green
