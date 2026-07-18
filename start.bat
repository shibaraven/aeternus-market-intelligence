@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Aeternus Market Intelligence - Source Start

echo.
echo === Aeternus Market Intelligence - Source Start ===
echo.

rem This file is for running the source version.
rem It must NOT call PyInstaller. If you see "Build EXE", you are running the wrong BAT.

if not exist "backend\app.py" (
    echo [ERROR] backend\app.py does not exist.
    echo Please extract/copy the complete project folder first.
    echo Required structure:
    echo   start.bat
    echo   backend\app.py
    echo   backend\main.py
    echo   frontend\index.html
    pause
    exit /b 1
)

if not exist "backend\main.py" (
    echo [ERROR] backend\main.py does not exist.
    echo Please copy the fixed backend\main.py into the backend folder.
    pause
    exit /b 1
)

if not exist "frontend\index.html" (
    echo [ERROR] frontend\index.html does not exist.
    echo Please extract/copy the complete project folder first.
    pause
    exit /b 1
)

set "PY_BOOT="
py -3.13 --version >nul 2>&1 && set "PY_BOOT=py -3.13"
if not defined PY_BOOT py -3.12 --version >nul 2>&1 && set "PY_BOOT=py -3.12"
if not defined PY_BOOT py -3.11 --version >nul 2>&1 && set "PY_BOOT=py -3.11"
if not defined PY_BOOT py --version >nul 2>&1 && set "PY_BOOT=py"
if not defined PY_BOOT python --version >nul 2>&1 && set "PY_BOOT=python"

if not defined PY_BOOT (
    echo [ERROR] Python not found.
    echo Please install Python 3.11, 3.12, or 3.13 from python.org, and enable Add Python to PATH.
    pause
    exit /b 1
)

echo [OK] Python command: %PY_BOOT%

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating local virtual environment...
    %PY_BOOT% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        pause
        exit /b 1
    )
)

set "PY_EXE=%CD%\.venv\Scripts\python.exe"

echo [2/4] Installing packages...
"%PY_EXE%" -m pip install --upgrade pip --disable-pip-version-check
"%PY_EXE%" -m pip install -r "backend\requirements.txt" --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] pip install failed.
    echo If you are using Python 3.14 and packages fail, install Python 3.12 or 3.13 and delete the .venv folder, then run start.bat again.
    pause
    exit /b 1
)

if not exist "data" mkdir "data"
if not exist "data\reports" mkdir "data\reports"

set "AETERNUS_DATA=%CD%\data"
set "AETERNUS_FRONTEND=%CD%\frontend"

echo [3/4] Starting server...
echo [4/4] Browser will open at http://127.0.0.1:5000
echo.
echo Press Ctrl+C to stop the server.
echo.

"%PY_EXE%" "backend\main.py"

echo.
echo Server stopped.
pause
