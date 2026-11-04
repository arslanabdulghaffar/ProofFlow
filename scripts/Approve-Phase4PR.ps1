$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Project Python environment is unavailable. No action performed.'
}
& $pythonPath (Join-Path $PSScriptRoot 'approve_phase4_pr_locally.py')
if ($LASTEXITCODE -ne 0) {
    throw 'Approval stopped. Keep the displayed status for reconciliation; do not retry blindly.'
}
