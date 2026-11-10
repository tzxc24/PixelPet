param()
$ErrorActionPreference='Stop'
$projectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$config=Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'tmp/device-lan-private.json') | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($config.token)) { throw 'Missing local device access token.' }
if (Get-NetTCPConnection -State Listen -LocalAddress $config.host -LocalPort $config.port -ErrorAction SilentlyContinue) {
    Write-Host "PixelPet device service is already listening at $($config.host):$($config.port)"
    exit 0
}
$env:PIXELPET_ACCESS_TOKEN=$config.token
$env:PIXELPET_ALLOWED_HOSTS="localhost,127.0.0.1,::1,$($config.host)"
Push-Location -LiteralPath $projectRoot
try {
    Write-Host "PixelPet device service at http://$($config.host):$($config.port)"
    & (Join-Path $projectRoot '.venv/Scripts/python.exe') -m uvicorn backend.main:app --host $config.host --port $config.port --ws-max-size 16384 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'PixelPet device service exited unexpectedly.' }
} finally {
    Pop-Location
}
