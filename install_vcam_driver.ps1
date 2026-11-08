<#
.SYNOPSIS
    Installs the Unity Capture DirectShow filter as "PixelMorph" virtual camera.
    Run this as Administrator ONCE after installing PixelMorph.

    After installation, PixelMorph app sends face-swapped frames to this
    virtual camera. Any app (Zoom, Teams, WhatsApp, OBS, etc.) sees
    "PixelMorph" as a camera source.

    To uninstall: run Uninstall.bat in the UnityCapture folder.
#>

#Requires -RunAsAdministrator

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PixelMorph Virtual Camera Driver Installer" -ForegroundColor Cyan
Write-Host "  Installs Unity Capture as 'PixelMorph'" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ucDir = Join-Path $scriptDir "UnityCapture"
$dll32 = Join-Path $ucDir "UnityCaptureFilter32.dll"
$dll64 = Join-Path $ucDir "UnityCaptureFilter64.dll"

# Verify DLLs exist
if (-not (Test-Path $dll64)) {
    Write-Host "✗ UnityCaptureFilter64.dll not found at: $dll64" -ForegroundColor Red
    Write-Host "  Make sure the UnityCapture folder is present." -ForegroundColor Red
    exit 1
}

Write-Host "Found Unity Capture DLLs at: $ucDir" -ForegroundColor Green
Write-Host ""

# Register 64-bit DLL with custom name "PixelMorph"
Write-Host "[1/2] Registering 64-bit Unity Capture filter as 'PixelMorph'..." -ForegroundColor Yellow
$result64 = regsvr32 /s "`"$dll64`"" "/i:UnityCaptureName=PixelMorph"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ 64-bit filter registered successfully" -ForegroundColor Green
} else {
    Write-Host "  ✗ 64-bit registration failed (rc=$LASTEXITCODE)" -ForegroundColor Red
    Write-Host "  Trying manual registry approach..."
    # Fallback: try without the /i parameter and set manually
    $result64 = regsvr32 /s "`"$dll64`""
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ 64-bit filter registered (default name)" -ForegroundColor Green
    }
}

# Register 32-bit DLL
if (Test-Path $dll32) {
    Write-Host "[2/2] Registering 32-bit Unity Capture filter..." -ForegroundColor Yellow
    $result32 = regsvr32 /s "`"$dll32`"" "/i:UnityCaptureName=PixelMorph"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ 32-bit filter registered successfully" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ 32-bit registration failed (non-critical on 64-bit OS)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/2] 32-bit DLL not found, skipping (64-bit is sufficient)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Verification ===" -ForegroundColor Cyan

# Verify the filter is registered
$clsidPath = "HKLM:\SOFTWARE\Classes\CLSID\{9E2655B1-6D1C-46bf-B23C-5CE92FC597B2}"
if (Test-Path $clsidPath) {
    $name = (Get-ItemProperty -Path $clsidPath -Name "(default)" -ErrorAction SilentlyContinue).'(default)'
    Write-Host "✓ CLSID registered: $name" -ForegroundColor Green
    
    $dshowPath = "HKLM:\SOFTWARE\Classes\CLSID\{9E2655B1-6D1C-46bf-B23C-5CE92FC597B2}\InprocServer32"
    if (Test-Path $dshowPath) {
        $dllPath = (Get-ItemProperty -Path $dshowPath -Name "(default)" -ErrorAction SilentlyContinue).'(default)'
        Write-Host "  DLL: $dllPath" -ForegroundColor Gray
    }
    
    Write-Host ""
    Write-Host "✓ PixelMorph virtual camera is now available in ALL apps!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Run PixelMorph: python pixelmorph.py" -ForegroundColor White
    Write-Host "  2. Load a source face" -ForegroundColor White  
    Write-Host "  3. Press START" -ForegroundColor White
    Write-Host "  4. Open Zoom/Teams/WhatsApp/OBS and select 'PixelMorph' as camera" -ForegroundColor White
    Write-Host ""
    Write-Host "NOTE: If you ever uninstall, run UnityCapture\Uninstall.bat as Admin" -ForegroundColor Yellow
} else {
    Write-Host "✗ Registration verification failed" -ForegroundColor Red
    Write-Host "  Try running: regsvr32 `"$dll64`"" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to exit"