param()
$ErrorActionPreference='Stop'
$projectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dependency=Join-Path $projectRoot 'tmp/esp-sr-reference'
$revision='b6774a31118de04742e51ab57dd68c9001fa1091'
if (!(Test-Path -LiteralPath (Join-Path $dependency '.git'))) {
    & git clone --depth 1 --filter=blob:none --sparse https://github.com/espressif/esp-sr.git $dependency
    if ($LASTEXITCODE -ne 0) { throw 'ESP-SR clone failed.' }
}
$current=& git -C $dependency rev-parse HEAD
if ($current -ne $revision) {
    $changes=& git -C $dependency status --porcelain
    if ($changes) { throw 'ESP-SR checkout has local changes. Review them before updating.' }
    & git -C $dependency fetch --depth 1 origin $revision
    if ($LASTEXITCODE -ne 0) { throw 'Cannot fetch the pinned ESP-SR revision.' }
    & git -C $dependency checkout --detach $revision
    if ($LASTEXITCODE -ne 0) { throw 'Cannot select the pinned ESP-SR revision.' }
}
& git -C $dependency sparse-checkout set include/esp32s3 lib/esp32s3
if ($LASTEXITCODE -ne 0) { throw 'Cannot fetch ESP32-S3 VAD headers and libraries.' }
if (!(Test-Path -LiteralPath (Join-Path $dependency 'lib/esp32s3/libesp_audio_processor.a'))) {
    throw 'ESP-SR VAD archive is missing.'
}
Write-Host "ESP-SR dependency ready at pinned revision $revision"
