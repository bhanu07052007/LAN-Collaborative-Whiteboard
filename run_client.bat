@echo off
title LAN Collaborative Whiteboard - Client
setlocal EnableDelayedExpansion

echo ========================================================
echo   Launching LAN Collaborative Whiteboard Client
echo ========================================================

:: Ensure we run from the project directory
cd /d "%~dp0"
set PYTHONPATH=%CD%

:: Check Python availability
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in PATH.
    echo Please install Python 3.10+ and add it to system PATH.
    pause
    exit /b 1
)

:: Run Client module
python -m client.main %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Client application exited with code %ERRORLEVEL%.
    pause
)
