# Interactive owner setup. Never paste a key into chat or a command argument.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Windows user-bound DPAPI is required.'
}
$credentialRoot = Join-Path $env:USERPROFILE '.proofflow\credentials'
$directory = Get-Item -LiteralPath $credentialRoot -Force
if (-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Use the existing ordinary ProofFlow credential directory.'
}
$ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
# Preserve unrelated descriptor sections and persist only changed owner/DACL sections.
# The PowerShell Set-Acl provider requested unavailable auditing privileges on this host.
$acl = Get-Acl -LiteralPath $credentialRoot
$acl.SetOwner($ownerSid)
$acl.SetAccessRuleProtection($true, $false)
foreach ($existingRule in @($acl.Access)) { $acl.RemoveAccessRuleAll($existingRule) }
foreach ($sid in @($ownerSid, $systemSid)) {
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
}
$directory.SetAccessControl($acl)
$destination = Join-Path $credentialRoot 'github-app.dpapi'
$metadata = Join-Path $credentialRoot 'github-app.json'
if ((Test-Path -LiteralPath $destination) -or (Test-Path -LiteralPath $metadata)) {
    throw 'Existing App configuration is preserved. Review rotation separately.'
}
$clientId = Read-Host 'GitHub App Client ID (not a secret)'
$installationId = Read-Host 'Installation ID (number in the installed App settings URL)'
if ($clientId -notmatch '^[A-Za-z0-9_.-]{1,64}$' -or $installationId -notmatch '^[1-9][0-9]{0,18}$') {
    throw 'Invalid non-secret App identifiers.'
}
$pemPath = Read-Host 'Full path to the downloaded App private-key PEM file (do not paste its contents)'
$item = Get-Item -LiteralPath $pemPath -Force
if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
    $item.Length -lt 512 -or $item.Length -gt 32768) {
    throw 'Expected an ordinary bounded PEM file.'
}
$raw = [IO.File]::ReadAllText($item.FullName)
if ($raw -notmatch '^-----BEGIN (RSA )?PRIVATE KEY-----') { throw 'Expected a GitHub App RSA private key.' }
$secret = ConvertTo-SecureString -String $raw -AsPlainText -Force
try {
    $encrypted = ConvertFrom-SecureString -SecureString $secret
    $config = @{client_id=$clientId; installation_id=$installationId;
        owner='arslanabdulghaffar'; repository='ProofFlow-Demo'; base='main'; path='pipeline.py'}
    foreach ($entry in @(@{path=$destination; text=$encrypted},
                          @{path=$metadata; text=($config | ConvertTo-Json -Compress)})) {
        $stream = [IO.File]::Open($entry.path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
        try {
            $bytes = [Text.Encoding]::UTF8.GetBytes($entry.text)
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
        } finally { $stream.Dispose() }
        $fileAcl = Get-Acl -LiteralPath $entry.path
        $fileAcl.SetOwner($ownerSid); $fileAcl.SetAccessRuleProtection($true, $false)
        foreach ($existingRule in @($fileAcl.Access)) { $fileAcl.RemoveAccessRuleAll($existingRule) }
        foreach ($sid in @($ownerSid, $systemSid)) {
            $fileAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', 'Allow'))
        }
        (Get-Item -LiteralPath $entry.path -Force).SetAccessControl($fileAcl)
    }
    Write-Host 'Saved encrypted App key and non-secret configuration outside Git.'
    Write-Host 'Tell Codex only: GitHub App saved. Do not send key contents.'
    Write-Host 'The original downloaded PEM was preserved; keep it private.'
} finally {
    $secret.Dispose()
    $raw = $null
}
