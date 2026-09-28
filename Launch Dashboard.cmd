@echo off
setlocal
title Meyaya Dashboard
cd /d "%~dp0"
if not exist ".venv-win\Scripts\python.exe" (
    echo Meyaya's Python environment was not found.
    echo Expected: .venv-win\Scripts\python.exe
    echo Set up the project environment before opening the dashboard.
    pause
    exit /b 1
)
echo Starting Meyaya's local dashboard...
echo Your browser will open when it is ready.
echo Keep this window open. Press Ctrl+C to stop the dashboard.
echo.
".venv-win\Scripts\python.exe" dashboard.py --open-browser
if errorlevel 1 (
    echo.
    echo Dashboard failed to start. Check the message above.
    pause
    exit /b 1
)
endlocal
