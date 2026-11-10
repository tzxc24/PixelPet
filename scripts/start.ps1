param([ValidateRange(1024,65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python environment missing. Follow README.md to create .venv and install requirements.'
}
$address = "http://127.0.0.1:$Port"
Push-Location -LiteralPath $projectRoot
try {
    $expectedVersion = & $pythonPath -c 'from backend.release import VERSION; print(VERSION)'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the PixelPet version from this environment.' }
} finally {
    Pop-Location
}
$probe = New-Object System.Net.Sockets.TcpClient
try {
    $probe.Connect('127.0.0.1', $Port)
    $occupied = $probe.Connected
} catch {
    $occupied = $false
} finally {
    $probe.Dispose()
}
if ($occupied) {
    $isPixelPet = $false
    try {
        $status = Invoke-RestMethod -Uri "$address/api/status" -TimeoutSec 2
        $schema = Invoke-RestMethod -Uri "$address/openapi.json" -TimeoutSec 2
        $isPixelPet = ($schema.info.title -like 'PixelPet*') -and ($status.mode -in @('mock','deepseek','openai')) -and $status.persistent_history -and $status.streaming
    } catch {
        $isPixelPet = $false
    }
    if ($isPixelPet) {
        Write-Host "PixelPet is already running at $address (version $($status.version))"
        if ($status.version -ne $expectedVersion) {
            Write-Warning "Existing instance is version $($status.version); this checkout is $expectedVersion. Stop the old instance before starting this release."
            exit 4
        }
        Write-Host 'Open that page in your browser; no second server is needed.'
        return
    }
    Write-Warning "Port $Port is already in use by another service, or the existing instance requires an access token."
    Write-Host "Use a different port: powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Port $($Port + 1)"
    exit 2
}
$dependencyCheck = @'
from importlib.util import find_spec
modules = ('uvicorn', 'fastapi', 'sqlalchemy', 'pydantic_settings', 'dotenv', 'openai', 'av', 'faster_whisper', 'edge_tts', 'python_multipart', 'websockets')
missing = [module for module in modules if find_spec(module) is None]
if missing:
    print('Missing dependencies: ' + ', '.join(missing))
    raise SystemExit(1)
'@
& $pythonPath -c $dependencyCheck
if ($LASTEXITCODE -ne 0) {
    Write-Host ('Install dependencies: "{0}" -m pip install -r "{1}"' -f $pythonPath, (Join-Path $projectRoot 'requirements.txt'))
    exit 3
}
Push-Location -LiteralPath $projectRoot
try {
    Write-Host "PixelPet $expectedVersion at $address  (Ctrl+C to stop)"
    & $pythonPath -m scripts.run_server --port $Port
    if ($LASTEXITCODE -ne 0) { throw "PixelPet exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
