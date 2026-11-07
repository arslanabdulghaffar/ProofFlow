# Password is entered only at the hidden local terminal prompt, never in chat/argv/Git.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONPATH = $projectRoot
& (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'export_portable_backup.py')
if ($LASTEXITCODE -ne 0) { throw 'PORTABLE_EXPORT_NOT_COMPLETED' }
