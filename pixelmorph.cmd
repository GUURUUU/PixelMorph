@echo off
setlocal enabledelayedexpansion

title PixelMorph — Face Swap + Virtual Camera

:: ── Verify Python ──
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: ── Change to script directory ──
cd /d "%~dp0"

:: ── Banner ──
echo.
echo   ╔══════════════════════════════════════╗
echo   ║          PixelMorph  v1.0            ║
echo   ║   Face Swap + Virtual Camera         ║
echo   ╚══════════════════════════════════════╝
echo.
echo   Virtual camera appears in ALL apps
echo   once you press START in PixelMorph.
echo.
echo   Close the PixelMorph window to stop.
echo.

:: ── Launch PixelMorph ──
python pixelmorph.py

:: ── PixelMorph_WhatsApp helper ──
if "%~1"=="--whatsapp" (
    call "%~dp0PixelMorph_WhatsApp.bat"
)

endlocal
