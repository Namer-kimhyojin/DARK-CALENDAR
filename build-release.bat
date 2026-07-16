@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_pipeline.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Dark Calendar release build failed. Exit code: %EXIT_CODE%
    if "%~1"=="" pause
    exit /b %EXIT_CODE%
)

echo.
echo Dark Calendar release build completed.
if "%~1"=="" pause
exit /b 0
