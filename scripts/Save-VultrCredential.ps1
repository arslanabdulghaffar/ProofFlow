# Run interactively as the Windows project owner. Never pass a secret as an argument.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Management', 'Inference')]
    [string]$Kind
)

$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'This helper requires Windows user-bound DPAPI encryption.'
}
$credentialRoot = Join-Path $env:USERPROFILE '.proofflow\credentials'
$credentialParent = Split-Path -Parent $credentialRoot
foreach ($folder in @($credentialParent, $credentialRoot)) {
    if (Test-Path -LiteralPath $folder) {
        $item = Get-Item -LiteralPath $folder -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Credential path must be an ordinary local directory.'
        }
    } else {
        $null = New-Item -ItemType Directory -Path $folder
    }
}
$ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$acl = [Security.AccessControl.DirectorySecurity]::new()
$acl.SetOwner($ownerSid)
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($ownerSid, $systemSid)) {
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'
    )
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $credentialRoot -AclObject $acl
$destination = Join-Path $credentialRoot ('vultr-' + $Kind.ToLowerInvariant() + '.dpapi')
if (Test-Path -LiteralPath $destination) {
    throw 'A credential already exists. Keep it; review rotation separately.'
}
$secret = Read-Host "Paste the Vultr $Kind API key (input is hidden)" -AsSecureString
try {
    if ($secret.Length -lt 1 -or $secret.Length -gt 512) {
        throw 'Key must contain between 1 and 512 characters.'
    }
    $encrypted = ConvertFrom-SecureString -SecureString $secret
    # CreateNew prevents accidental replacement. The restricted directory supplies the ACL.
    $stream = [IO.File]::Open($destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($encrypted)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally {
        $stream.Dispose()
    }
    # Elevated Windows terminals otherwise assign the Administrators group as owner.
    $fileAcl = [Security.AccessControl.FileSecurity]::new()
    $fileAcl.SetOwner($ownerSid)
    $fileAcl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($ownerSid, $systemSid)) {
        $fileAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $sid, 'FullControl', 'Allow'
        ))
    }
    Set-Acl -LiteralPath $destination -AclObject $fileAcl
    Write-Host "Saved encrypted $Kind key for this Windows user only: $destination"
    Write-Host 'Tell Codex only that the key is saved. Do not paste it into chat.'
} finally {
    $secret.Dispose()
}
