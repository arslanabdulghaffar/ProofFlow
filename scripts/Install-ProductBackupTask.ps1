# Owner-authorized private project backup. Runs under existing interactive user, no password.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'Run-ProductBackup.ps1'
$taskName = 'ProofFlow-ProductBackup'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'EXISTING_BACKUP_TASK_REQUIRES_RECONCILIATION' }
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -File "' + $scriptPath + '"')
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Private encrypted ProofFlow product backup. Check hourly, capture at most every 12 hours; retry visibly when closed/idle gate is unavailable.' | Out-Null
$saved = Get-ScheduledTask -TaskName $taskName
if ($saved.Actions.Execute -ne $action.Execute -or $saved.Actions.Arguments -ne $action.Arguments -or $saved.Principal.LogonType -ne 'Interactive') { throw 'BACKUP_TASK_READBACK_FAILED' }
Write-Output 'BACKUP_TASK_INSTALLED_CURRENT_USER_HOURLY_NO_STORED_PASSWORD'
