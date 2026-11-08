@echo off
title PixelMorph ? e2eSoft VCam ? Snap Camera Bridge
echo ============================================
echo   PixelMorph Snap Camera Bridge
echo ============================================
echo.

REM Step 1: Start PixelMorph (face swap app)
echo [1/4] Starting PixelMorph...
start "" python "%USERPROFILE%\Desktop\PixelMorph\pixelmorph.py"

REM Wait for PixelMorph to start
echo       Waiting 10s for PixelMorph to initialize...
ping -n 10 127.0.0.1 > nul

echo.
echo [2/4] IMPORTANT: In PixelMorph window:
echo       - Load a source face image
echo       - Click START to begin face swap
echo       - Verify the preview shows face-swapped video
echo.
echo [3/4] Then open e2eSoft VCam Manager:
echo       - Select OBS Virtual Camera as source
echo       - Click PLAY button
echo.
echo [4/4] Open Snap Camera - select "e2eSoft VCam"
echo.
pause
start "" "C:\Program Files (x86)\e2eSoft\VCam\VCamMain.exe"
echo.
echo ============================================
echo   Pipeline ready! Use Snap Camera with lenses
echo ============================================
pause
