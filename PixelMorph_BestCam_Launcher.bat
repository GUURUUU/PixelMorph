@echo off
title PixelMorph + BestCam Bridge

echo ============================================
echo   PixelMorph + BestCam Virtual Camera
echo   (No watermark!)
echo ============================================
echo.

REM Step 1: Kill any old BestCamHost instances (keep trying)
echo [INFO] Stopping old BestCamHost instances...
taskkill /F /IM BestCamHost.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM Step 2: Start BestCamHost with VISIBLE console window
REM   CRITICAL: -WindowStyle must be Normal (NOT Hidden).
REM   Hidden windows cause getchar() to return EOF immediately,
REM   which shuts down the camera as soon as it starts.
echo [INFO] Starting BestCamHost (visible window - DO NOT CLOSE)...
net session >nul 2>&1
if %errorLevel% neq 0 (
    REM Need admin - use RunAs with NORMAL window (not Hidden!)
    powershell -NoProfile -Command "Start-Process -FilePath 'C:\Program Files\BestCam\BestCamHost.exe' -Verb RunAs -WindowStyle Normal"
) else (
    REM Already admin - start normally
    start "BestCamHost" "C:\Program Files\BestCam\BestCamHost.exe"
)

echo [WAIT] Waiting for BestCam virtual camera to initialize...
timeout /t 3 /nobreak >nul

REM Step 3: Start the bridge and stream frames
echo [INFO] Starting BestCam frame bridge...
start "BestCam Bridge" python "%~dp0scripts\test_bestcam_live.py"

REM Step 4: Start PixelMorph
echo [INFO] Starting PixelMorph...
start "" python "%~dp0pixelmorph.py"

echo.
echo ============================================
echo   Pipeline ready!
echo ============================================
echo.
echo   IMPORTANT:
echo   - Keep the BestCamHost console window OPEN
echo   - It will say "Press ENTER to stop" - DON'T press ENTER
echo   - Just minimize it if it's in the way
echo.
echo   Snap Camera: Select "BestCam Virtual Webcam" as camera
echo.
echo   To stop: Close PixelMorph, then press ENTER on BestCamHost
echo.
pause
