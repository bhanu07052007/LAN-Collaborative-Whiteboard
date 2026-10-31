@echo off
title LAN Collaborative Whiteboard - Server
setlocal EnableDelayedExpansion

echo ========================================================
echo   Launching LAN Collaborative Whiteboard Server
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

:: Run Server module
python -m server.main %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Server exited with code %ERRORLEVEL%.
    pause
)
