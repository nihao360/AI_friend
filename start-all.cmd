@echo off
rem Launch AI companion stack (QQ -> SnowLuma -> MaiBot)
rem Chinese output lives in start-all.ps1 (UTF-8 with BOM)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1"
if errorlevel 1 pause
