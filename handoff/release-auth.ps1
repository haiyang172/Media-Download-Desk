$ErrorActionPreference = 'Stop'
$env:GIT_TERMINAL_PROMPT = '0'
$input = "protocol=https`nhost=github.com`n`n"
$cred = $input | git credential fill 2>$null
if (-not $cred) { 'NO_CREDENTIAL'; exit 1 }
$token = ($cred | Where-Object { $_ -like 'password=*' }) -replace '^password=', ''
$user = ($cred | Where-Object { $_ -like 'username=*' }) -replace '^username=', ''
if (-not $token) { 'NO_TOKEN'; exit 1 }
"credential found: user=$user length=$($token.Length) prefix=$($token.Substring(0,4))"
$headers = @{ Authorization = "token $token"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'amdl-release' }
try {
    $me = Invoke-RestMethod -Uri 'https://api.github.com/user' -Headers $headers -TimeoutSec 30
    "auth OK as: $($me.login)"
} catch {
    "auth FAILED: $($_.Exception.Message)"
    exit 1
}
try {
    $scopes = (Invoke-WebRequest -Uri 'https://api.github.com/user' -Headers $headers -TimeoutSec 30).Headers['X-OAuth-Scopes']
    "oauth scopes: $scopes"
} catch { "scopes unknown" }
