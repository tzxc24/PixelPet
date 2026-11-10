$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python environment missing. Follow README.md to create .venv and install requirements.'
}
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
