@echo off
cd /d "%~dp0"

docker compose down

echo.
echo Bag Counter stopped.
echo.

pause