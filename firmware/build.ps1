param(
 [ValidateSet('build','menuconfig','flash','monitor')][string]$Action='build',
 [ValidatePattern('^COM[1-9][0-9]*$')][string]$Port,
 [string]$SdkConfig
)
$ErrorActionPreference='Stop'
if($Action -in @('flash','monitor') -and !$Port){throw 'Specify the verified serial port with -Port COMn.'}
$projectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($SdkConfig) {
 $SdkConfig=(Resolve-Path -LiteralPath $SdkConfig).Path
 if (Select-String -Quiet -LiteralPath $SdkConfig -Pattern '^CONFIG_PIXELPET_USE_ESP_SR_VAD=y$') {
  & (Join-Path $PSScriptRoot 'setup_esp_sr.ps1')
  if ($LASTEXITCODE -ne 0) { throw 'ESP-SR dependency setup failed.' }
 }
}
$env:IDF_PATH=Join-Path $projectRoot 'tmp\esp-idf'
$env:IDF_TOOLS_PATH=Join-Path $projectRoot 'tmp\idf-tools'
$env:TEMP=Join-Path $projectRoot 'tmp'
$env:TMP=$env:TEMP
$env:PIP_CACHE_DIR=Join-Path $projectRoot 'tmp\pip-cache'
$env:IDF_COMPONENT_MANAGER='0'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$basePython=Join-Path $projectRoot 'tmp\python\cpython-3.10-windows-x86_64-none\python.exe'
$idfPython=Join-Path $env:IDF_TOOLS_PATH 'python_env\idf6.1_py3.10_env\Scripts\python.exe'
if(!(Test-Path -LiteralPath $idfPython)){throw 'Install ESP-IDF v6.1 and Python tools per docs/firmware_build.md first.'}
$exported=& $basePython (Join-Path $env:IDF_PATH 'tools\idf_tools.py') export --format key-value
if($LASTEXITCODE -ne 0){throw 'ESP-IDF export failed'}
foreach($entry in $exported){
 if($entry -match '^([A-Z_]+)=(.*)$'){
  $idfVariable=$Matches[1]
  $idfValue=$Matches[2].Replace('%PATH%',$env:PATH)
  Set-Item -Path "Env:$idfVariable" -Value $idfValue
 }
}
Set-Location -LiteralPath $projectRoot
$arguments=@('-C',(Join-Path $projectRoot 'firmware\pixelpet_s3'),'-B',(Join-Path $projectRoot 'tmp\firmware-build'))
if($SdkConfig){$arguments+=@('-D',('SDKCONFIG='+$SdkConfig.Replace('\','/')))}
if($Port){$arguments+=@('-p',$Port)}
& $idfPython (Join-Path $env:IDF_PATH 'tools\idf.py') @arguments $Action
exit $LASTEXITCODE
