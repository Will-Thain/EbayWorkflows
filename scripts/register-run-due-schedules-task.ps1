# Register Windows Task Scheduler job to run ebay-workflows run-due-schedules every 5 minutes.
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$Python = (Get-Command python -ErrorAction Stop).Source
$TaskName = "EbayWorkflows-RunDueSchedules"
$Action = New-ScheduledTaskAction -Execute $Python -Argument "-m ebay_workflows.scheduler" -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
Write-Host "Registered scheduled task: $TaskName"
Write-Host "  Python: $Python"
Write-Host "  WorkingDirectory: $RepoRoot"
Write-Host "  Interval: every 5 minutes"
Write-Host "Test now: python -m ebay_workflows.scheduler"
