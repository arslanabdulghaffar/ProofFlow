# Existing private desktop credentials only. No secrets in Task Scheduler arguments.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$privateRoot = Join-Path $env:USERPROFILE '.proofflow\deployment'
$reportPath = Join-Path $privateRoot 'scheduled-backup-task-last.json'
try {
    Set-Location -LiteralPath $projectRoot
    $env:PYTHONPATH = $projectRoot
    $result = & (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'scheduled_product_backup.py') 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'BACKUP_RETRY_OR_RECONCILE_REQUIRED' }
    $parsed = $result | ConvertFrom-Json
    if ($parsed.scheduled_backup -notin @('captured','not_due')) { throw 'BACKUP_RESULT_INVALID' }
    [IO.File]::WriteAllText($reportPath, (@{status=$parsed.scheduled_backup; checked_at=[DateTime]::UtcNow.ToString('o'); expires_at=$parsed.expires_at} | ConvertTo-Json))
} catch {
    [IO.File]::WriteAllText($reportPath, (@{status='RETRY_OR_RECONCILE_REQUIRED'; checked_at=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json))
    exit 1
}
