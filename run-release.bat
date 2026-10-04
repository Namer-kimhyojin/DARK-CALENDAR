@echo off
cd /d "%~dp0"
if not exist "dist\x64\DarkCalendar\DarkCalendar.exe" (
    echo Release not found. Run build-release.bat first.
    pause
    exit /b 1
)
start "Air Calendar" "dist\x64\DarkCalendar\DarkCalendar.exe" %*
