@echo off
REM Cmd.exe-callable wrapper for install.ps1.
REM Lets users on the default Windows console kick off the installer without
REM having to switch to PowerShell or touch the execution policy by hand.

setlocal
set HERE=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%install.ps1" %*
exit /b %ERRORLEVEL%
