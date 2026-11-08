<#
.SYNOPSIS
    Install BestCam as the watermark-free virtual camera for PixelMorph → Snap Camera.
    Run this as Administrator ONCE.
#>

#Requires -RunAsAdministrator

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  BestCam Virtual Camera Installer" -ForegroundColor Cyan
Write-Host "  Watermark-free replacement for e2eSoft VCam" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$buildDir = Join-Path $PSScriptRoot "BestCam\build\Release"
$deployDir = "C:\Program Files\BestCam"

# Step 1: Deploy files
Write-Host "[1/4] Deploying BestCam files..." -ForegroundColor Yellow
if (-not (Test-Path $deployDir)) {
    New-Item -ItemType Directory -Path $deployDir -Force | Out-Null
}
Copy-Item "$buildDir\BestCamSource.dll" "$deployDir\" -Force
Copy-Item "$buildDir\BestCamHost.exe" "$deployDir\" -Force
Write-Host "  ✓ Files deployed to $deployDir" -ForegroundColor Green

# Step 2: Register COM server
Write-Host "[2/4] Registering BestCamSource.dll..." -ForegroundColor Yellow
regsvr32 /s "$deployDir\BestCamSource.dll"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Registered successfully" -ForegroundColor Green
} else {
    Write-Host "  ✗ Registration failed (exit code: $LASTEXITCODE)" -ForegroundColor Red
}

# Step 3: Start the virtual camera with VISIBLE console window
#   CRITICAL: Must NOT be Hidden. Hidden causes getchar() → EOF → camera shutdown.
Write-Host "[3/4] Starting BestCam Virtual Camera..." -ForegroundColor Yellow
Write-Host "  (A console window will appear - keep it open)" -ForegroundColor Yellow
$hostProc = Start-Process -FilePath "$deployDir\BestCamHost.exe" -WindowStyle Normal -PassThru
Start-Sleep -Seconds 3

if ($hostProc.HasExited) {
    Write-Host "  ✗ BestCamHost exited immediately" -ForegroundColor Red
    Write-Host "  Check if another BestCamHost is already running (taskkill /F /IM BestCamHost.exe first)"
    exit 1
} else {
    Write-Host "  ✓ BestCamHost running (PID: $($hostProc.Id))" -ForegroundColor Green
    $hostProc.Id | Out-File "$deployDir\pid.txt"
}

# Step 4: Test the camera appears in MF enumeration
Write-Host "[4/4] Verifying virtual camera in MF device list..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Devices.Enumeration.DeviceInformation,Windows.Devices.Enumeration,ContentType=WindowsRuntime]
    $task = [Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync([Windows.Devices.Enumeration.DeviceClass]::VideoCapture)
    while (-not $task.IsCompleted) { Start-Sleep -Milliseconds 100 }
    $devices = $task.GetAwaiter().GetResult()
    $found = $devices | Where-Object { $_.Name -match "BestCam" }
    if ($found) {
        Write-Host "  ✓ 'BestCam Virtual Webcam' found in camera list!" -ForegroundColor Green
    } else {
        Write-Host "  ✗ BestCam NOT found in camera list" -ForegroundColor Red
        Write-Host "  Available cameras:"
        $devices | ForEach-Object { Write-Host "    - $($_.Name)" }
    }
} catch {
    Write-Host "  ! Could not enumerate MF cameras: $_" -ForegroundColor Yellow
    Write-Host "  (Camera may still work despite this)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Keep this PowerShell window OPEN (BestCamHost runs inside it)"
Write-Host "  2. Open PixelMorph → click START"
Write-Host "  3. Run the Python bridge: python bestcam_bridge.py"
Write-Host "  4. Open Snap Camera → select 'BestCam Virtual Webcam'"
Write-Host ""
Write-Host "To STOP: Press ENTER in this window or close it."
Write-Host ""

# Wait for user to press Enter (keeping the camera alive)
Read-Host "Press ENTER to stop the virtual camera and exit"

Write-Host "Stopping BestCam virtual camera..."
Stop-Process -Id $hostProc.Id -Force -ErrorAction SilentlyContinue
Write-Host "Done."
