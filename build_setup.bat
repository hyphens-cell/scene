@echo off
setlocal
cd /d "%~dp0"
set "SETUP_PS=powershell.exe"
where pwsh.exe >nul 2>&1
if not errorlevel 1 set "SETUP_PS=pwsh.exe"
"%SETUP_PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_setup.ps1" %*
exit /b %errorlevel%
