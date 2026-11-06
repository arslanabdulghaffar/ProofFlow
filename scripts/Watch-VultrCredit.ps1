# Trusted administrator scheduled task. No key, token or VM identity in output.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$guardPath = Join-Path $PSScriptRoot 'vultr_credit_guard.py'
$privateRoot = Join-Path $env:USERPROFILE '.proofflow\deployment'
$reportPath = Join-Path $privateRoot 'guard-last.json'
$guardFailed = $false
try {
    $result = & $pythonPath $guardPath 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'CREDIT_GUARD_RETRY_REQUIRED' }
    $parsed = $result | ConvertFrom-Json
    if (-not $parsed.credit_guard) { throw 'CREDIT_GUARD_INVALID_RESULT' }
    [IO.File]::WriteAllText($reportPath, ($parsed | ConvertTo-Json -Depth 5))
} catch {
    [IO.File]::WriteAllText($reportPath, (@{
        credit_guard = 'RETRY_REQUIRED'; checked_at = [DateTime]::UtcNow.ToString('o')
        detail = 'No provider hard-stop guarantee; inspect the project guard.'
    } | ConvertTo-Json))
    $guardFailed = $true
}
# Independent local backup-key expiry. Failure never overwrites the credit result.
$backupReport = Join-Path $privateRoot 'asset-backup-guard-last.json'
try {
    $backupResult = & $pythonPath (Join-Path $PSScriptRoot 'asset_backup_vault.py') 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'ASSET_BACKUP_EXPIRY_RECONCILIATION_REQUIRED' }
    $backupParsed = $backupResult | ConvertFrom-Json
    if ($backupParsed.asset_backup_expiry -ne 'checked') { throw 'ASSET_BACKUP_EXPIRY_INVALID' }
    [IO.File]::WriteAllText($backupReport, ($backupParsed | ConvertTo-Json -Depth 3))
} catch {
    [IO.File]::WriteAllText($backupReport, (@{
        asset_backup_expiry = 'RECONCILIATION_REQUIRED'
        checked_at = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json))
    exit 1
}
if ($guardFailed) { exit 1 }
