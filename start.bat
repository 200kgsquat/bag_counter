@echo off
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"

if errorlevel 1 (
    echo.
    echo Bag Counter failed to start.
    echo See the error above.
    echo.
    pause
    exit /b 1
)

echo.
echo Bag Counter started successfully.
echo You can close this window.
echo.
pause