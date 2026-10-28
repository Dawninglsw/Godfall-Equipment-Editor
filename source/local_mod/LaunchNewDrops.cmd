@echo off
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0launch_portable.ps1" -GroundLoot
if errorlevel 1 (
    echo Godfall Equipment Editor could not start. Check launcher_error.log in this folder.
    pause
    exit /b 1
)
exit /b 0
