# Administrator-only, read-only preflight. Emits no account identity, API key or passwords.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$credentialRoot = Join-Path $env:USERPROFILE '.proofflow\credentials'
$credentialFile = Join-Path $credentialRoot 'vultr-management.dpapi'
if (-not (Test-Path -LiteralPath $credentialFile)) {
    throw 'MANAGEMENT_KEY_NOT_SAVED: run Save-VultrCredential.ps1 interactively.'
}
$ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
foreach ($path in @((Split-Path -Parent $credentialRoot), $credentialRoot, $credentialFile)) {
    $item = Get-Item -LiteralPath $path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'UNSAFE_CREDENTIAL_PATH'
    }
}
$fileInfo = Get-Item -LiteralPath $credentialFile
if ($fileInfo.PSIsContainer -or $fileInfo.Length -gt 65536) { throw 'INVALID_CREDENTIAL_FILE' }
foreach ($path in @($credentialRoot, $credentialFile)) {
    $acl = Get-Acl -LiteralPath $path
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $ownerSid) {
        throw 'UNSAFE_CREDENTIAL_OWNER'
    }
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin @($ownerSid, 'S-1-5-18')) {
            throw 'UNSAFE_CREDENTIAL_ACCESS'
        }
    }
}
$secret = $null
$pointer = [IntPtr]::Zero
$client = $null
$handler = $null
try {
    $encrypted = [IO.File]::ReadAllText($credentialFile)
    $secret = ConvertTo-SecureString -String $encrypted
    if ($secret.Length -lt 1 -or $secret.Length -gt 512) { throw 'INVALID_KEY_LENGTH' }
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ($token -notmatch '^[\x21-\x7e]{1,512}$') { throw 'INVALID_KEY_FORMAT' }
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.UseProxy = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(20)
    $client.DefaultRequestHeaders.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $token)
    $client.DefaultRequestHeaders.UserAgent.ParseAdd('ProofFlow-Phase1-Preflight/1.0')
    $answers = @{}
    foreach ($route in @('account', 'instances?per_page=100', 'inference')) {
        $response = $client.GetAsync(('https://api.vultr.com/v2/' + $route), [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        try {
            if (-not $response.IsSuccessStatusCode) {
                throw ('VULTR_PREFLIGHT_HTTP_' + [int]$response.StatusCode)
            }
            $null = $response.Content.LoadIntoBufferAsync(2097152).GetAwaiter().GetResult()
            $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            $answers[$route] = ConvertFrom-Json -InputObject $raw
        } finally {
            $response.Dispose()
        }
    }
    $account = $answers['account'].account
    [ordered]@{
        scope = 'authenticated_read_only_no_provisioning_no_inference_call'
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        balance_api_value = $account.balance
        pending_charges = $account.pending_charges
        instance_count_on_first_page = @($answers['instances?per_page=100'].instances).Count
        inference_subscription_count = @($answers['inference'].subscriptions).Count
        note = 'API balance sign must be reconciled with console remaining credit; no expiry or hard-stop guarantee inferred.'
    } | ConvertTo-Json
} catch {
    # Never surface HTTP response text, headers, raw objects or provider diagnostics.
    $code = 'VULTR_PREFLIGHT_FAILED'
    if ($_.Exception.Message -match '^VULTR_PREFLIGHT_HTTP_[0-9]{3}$') { $code = $_.Exception.Message }
    throw $code
} finally {
    if ($client) { $client.Dispose() }
    if ($handler) { $handler.Dispose() }
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    if ($secret) { $secret.Dispose() }
    $token = $null
    $raw = $null
    $answers = $null
}
