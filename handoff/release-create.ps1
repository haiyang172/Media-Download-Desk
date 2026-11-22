$ErrorActionPreference = 'Continue'
Set-Location 'D:\AMDL'
$env:GIT_TERMINAL_PROMPT = '0'

$exe = 'D:\AMDL\installer\dist\0.3.40\MediaDownloadDesk-Setup.exe'
if (-not (Test-Path $exe)) { throw "missing installer: $exe" }
$size = (Get-Item $exe).Length
"installer bytes: $size"

$commit = (git rev-parse HEAD).Trim()
"commit: $commit"
if (-not (git tag --list 'v0.3.40')) {
    git tag -a v0.3.40 -m "MediaDownloadDesk v0.3.40" $commit
}
& git push origin v0.3.40 2>&1 | Out-Null
$remoteTag = (& git ls-remote origin refs/tags/v0.3.40 2>$null) -join ''
"tag pushed: " + $(if ($remoteTag) { 'yes' } else { 'no' })
$ErrorActionPreference = 'Stop'

$cred = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
$token = ($cred | Where-Object { $_ -like 'password=*' }) -replace '^password=', ''
$headers = @{ Authorization = "token $token"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'amdl-release' }

$notes = [IO.File]::ReadAllText('D:\AMDL\handoff\release-notes-0.3.40.txt', [Text.Encoding]::UTF8)
$release = $null
try {
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/haiyang172/Media-Download-Desk/releases/tags/v0.3.40' `
        -Headers $headers -TimeoutSec 30
    "release exists: id=$($release.id)"
} catch {
    $release = $null
}
if (-not $release) {
    $json = @{
        tag_name = 'v0.3.40'
        target_commitish = $commit
        name = 'MediaDownloadDesk v0.3.40 - Qt'
        body = $notes
        draft = $false
        prerelease = $false
    } | ConvertTo-Json -Depth 5
    $bodyBytes = [Text.Encoding]::UTF8.GetBytes($json)
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/haiyang172/Media-Download-Desk/releases' `
        -Method Post -Headers $headers -Body $bodyBytes -ContentType 'application/json; charset=utf-8' -TimeoutSec 60
    "release created: id=$($release.id) tag=$($release.tag_name)"
}

$existing = @($release.assets | Where-Object { $_.name -eq 'MediaDownloadDesk-Setup.exe' })
if ($existing.Count -gt 0 -and $existing[0].state -eq 'uploaded' -and $existing[0].size -eq $size) {
    "asset already uploaded: $([math]::Round($existing[0].size / 1MB, 1)) MB"
    return
}
foreach ($old in $existing) {
    Invoke-RestMethod -Uri "https://api.github.com/repos/haiyang172/Media-Download-Desk/releases/assets/$($old.id)" `
        -Method Delete -Headers $headers -TimeoutSec 30 | Out-Null
    "deleted incomplete asset $($old.id)"
}

$uploadUrl = "https://uploads.github.com/repos/haiyang172/Media-Download-Desk/releases/$($release.id)/assets?name=MediaDownloadDesk-Setup.exe"
$config = Join-Path $env:TEMP ("amdl-curl-" + [guid]::NewGuid().ToString('N') + ".cfg")
$exeCurl = $exe.Replace('\', '/')
$uploadCurl = $uploadUrl
$config = Join-Path $env:TEMP ("amdl-curl-" + [guid]::NewGuid().ToString('N') + ".cfg")
$lines = @(
    "url = `"$uploadCurl`"",
    "header = `"Authorization: token $token`"",
    "header = `"Content-Type: application/octet-stream`"",
    "header = `"User-Agent: amdl-release`"",
    "upload-file = `"$exeCurl`"",
    "silent",
    "show-error",
    "write-out = `"%{http_code}`""
)
Set-Content -LiteralPath $config -Value $lines -Encoding ASCII
$acl = Get-Acl $config
$acl.SetAccessRuleProtection($true, $false)
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
    [System.Security.Principal.WindowsIdentity]::GetCurrent().Name, 'FullControl', 'Allow')))
Set-Acl -LiteralPath $config -AclObject $acl

try {
    $code = & curl.exe --config $config 2>&1
    "upload http: $code"
} finally {
    Remove-Item -LiteralPath $config -Force -ErrorAction SilentlyContinue
}

$check = Invoke-RestMethod -Uri "https://api.github.com/repos/haiyang172/Media-Download-Desk/releases/$($release.id)" -Headers $headers -TimeoutSec 60
foreach ($a in $check.assets) {
    "asset: $($a.name) state=$($a.state) size=$([math]::Round($a.size / 1MB, 1)) MB"
}
