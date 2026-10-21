@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\manage_version.py check
if errorlevel 1 (
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 pause
