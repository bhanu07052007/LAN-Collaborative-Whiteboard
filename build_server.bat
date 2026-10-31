@echo off
title Build Standalone Server Executable
setlocal EnableDelayedExpansion

echo ========================================================
echo   Packaging LAN Whiteboard Server into server.exe
echo ========================================================

cd /d "%~dp0"
set PYTHONPATH=%CD%

where pyinstaller >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] PyInstaller not found. Installing now...
    pip install pyinstaller
)

echo Building server.exe...
pyinstaller --onefile ^
    --name server ^
    --clean ^
    --paths "%CD%" ^
    server\main.py

if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo   Build complete! Standalone executable located at:
    echo   %CD%\dist\server.exe
    echo ========================================================
) else (
    echo [ERROR] Build failed with exit code %ERRORLEVEL%.
)
pause
