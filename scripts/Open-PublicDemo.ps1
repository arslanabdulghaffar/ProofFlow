# Opens a dedicated signed-in guest browser. No key entry, credential output or auto approval.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -X utf8 (Join-Path $PSScriptRoot 'guest_demo.py') open
    if ($LASTEXITCODE -ne 0) { throw 'Demo setup stopped safely. Keep the status for reconciliation.' }
} finally { Pop-Location }
