@echo off
setlocal EnableExtensions
title Aeternus Market Intelligence Builder
cd /d "%~dp0"

echo.
echo === Aeternus Market Intelligence - Build EXE ===
echo.

py --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.11, 3.12, or 3.13 and enable Add Python to PATH.
    pause
    exit /b 1
)

echo [1/3] Installing pinned build packages...
py -m pip install -r "backend\requirements-build.txt" --quiet --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)

echo [2/3] Building EXE (5-10 min)...
py -m PyInstaller --noconfirm --clean --distpath "dist" --workpath "build_temp" "AeternusMarketIntelligence.spec"
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo [3/3] Finalizing...
if not exist "dist\AeternusMarketIntelligence\data" mkdir "dist\AeternusMarketIntelligence\data"
(
    echo Aeternus Market Intelligence
    echo Double-click AeternusMarketIntelligence.exe to start.
    echo The browser opens automatically at http://127.0.0.1:5000.
    echo Application data is created in the data folder on first launch.
) > "dist\AeternusMarketIntelligence\README.txt"

echo.
echo === Build Complete ===
echo Location: dist\AeternusMarketIntelligence\AeternusMarketIntelligence.exe
echo Copy the entire dist\AeternusMarketIntelligence folder to another PC.
echo.
pause
