@echo off
rem Stop AI companion services (keeps QQ running)
rem Chinese output lives in stop-all.ps1 (UTF-8 with BOM)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-all.ps1"
if errorlevel 1 pause
