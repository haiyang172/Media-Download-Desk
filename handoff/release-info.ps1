$ErrorActionPreference = 'Stop'
$env:GIT_TERMINAL_PROMPT = '0'
$cred = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
$token = ($cred | Where-Object { $_ -like 'password=*' }) -replace '^password=', ''
$headers = @{ Authorization = "token $token"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'amdl-release' }
$rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/haiyang172/Media-Download-Desk/releases/latest' -Headers $headers -TimeoutSec 30
"latest: $($rel.tag_name)  name=$($rel.name)"
foreach ($a in $rel.assets) { "  asset: $($a.name)  $([math]::Round($a.size/1MB,1)) MB  state=$($a.state)" }
"body:`n$($rel.body)"
