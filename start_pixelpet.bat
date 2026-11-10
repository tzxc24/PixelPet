@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
set "pixelpet_exit=%ERRORLEVEL%"
if not "%pixelpet_exit%"=="0" pause
exit /b %pixelpet_exit%
