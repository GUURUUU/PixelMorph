@echo off
title PixelMorph — WhatsApp Camera Helper
chcp 65001 >nul

echo ╔══════════════════════════════════════════╗
echo ║   PixelMorph — WhatsApp Camera Fix       ║
echo ╚══════════════════════════════════════════╝
echo.
echo Forces Chrome to use DirectShow for cameras
echo so PixelMorph appears in WhatsApp's list.
echo.
echo Make sure PixelMorph is RUNNING and STARTED
echo before selecting the camera in WhatsApp.
echo.

:: Kill any existing WhatsApp PWA instance
taskkill /F /FI "WINDOWTITLE eq WhatsApp*" /T 2>nul

:: Small delay to ensure clean launch
timeout /t 1 /nobreak >nul

echo Launching WhatsApp with DirectShow camera support...
echo.
start "" "C:\Program Files\Google\Chrome\Application\chrome_proxy.exe" ^
    --profile-directory=Default ^
    --app-id=hnpfjngllnobngcgfapefoaidbinmjnm ^
    --disable-features=MediaFoundationCamera ^
    --enable-features=WebRtcUseWinDshowCamera

echo.
echo WhatsApp launched. Go to Settings ^> Audio and Video
echo and select "PixelMorph" as the camera.
echo.
echo NOTE: You must run PixelMorph first and press START
echo before WhatsApp can see the virtual camera.
echo.
pause
