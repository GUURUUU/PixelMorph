#Requires -RunAsAdministrator
<#
  Restart BestCam: kill old instances, start fresh with visible window.
  Run this via: Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\restart_bestcam.ps1`""
#>

Write-Host "=== BestCam Restart Script ===" -ForegroundColor Cyan

# Step 1: Kill all old instances
Write-Host "[1/3] Killing old BestCamHost processes..." -ForegroundColor Yellow
Get-Process BestCamHost -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

if (Get-Process BestCamHost -ErrorAction SilentlyContinue) {
    taskkill /F /IM BestCamHost.exe 2>&1 | Out-Null
    Start-Sleep -Seconds 1
}
Write-Host "  Done" -ForegroundColor Green

# Step 2: Start BestCamHost with VISIBLE window
Write-Host "[2/3] Starting BestCamHost (visible console)..." -ForegroundColor Yellow
$hostPath = "C:\Program Files\BestCam\BestCamHost.exe"
if (-not (Test-Path $hostPath)) {
    Write-Host "  ERROR: $hostPath not found!" -ForegroundColor Red
    exit 1
}

$proc = Start-Process -FilePath $hostPath -WindowStyle Normal -PassThru
Write-Host "  Started PID $($proc.Id)" -ForegroundColor Green
Start-Sleep -Seconds 3

if ($proc.HasExited) {
    Write-Host "  WARNING: BestCamHost exited immediately!" -ForegroundColor Red
    Write-Host "  Check the console window for error messages" -ForegroundColor Red
    exit 1
}

# Step 3: Verify camera appears in MF enumeration
Write-Host "[3/3] Verifying camera in MF device list..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Devices.Enumeration.DeviceInformation,Windows.Devices.Enumeration,ContentType=WindowsRuntime]
    $asyncOp = [Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync([Windows.Devices.Enumeration.DeviceClass]::VideoCapture)
    while (-not $asyncOp.IsCompleted) { Start-Sleep -Milliseconds 200 }
    $devices = $asyncOp.GetAwaiter().GetResult()
    
    Write-Host "  Available MF cameras:" -ForegroundColor Cyan
    $found = $false
    foreach ($d in $devices) {
        $marker = ""
        $color = "White"
        if ($d.Name -match "BestCam") {
            $marker = " <<<---"
            $color = "Green"
            $found = $true
        }
        Write-Host "    - $($d.Name)$marker" -ForegroundColor $color
    }
    
    if ($found) {
        Write-Host "  SUCCESS: BestCam Virtual Webcam is in the camera list!" -ForegroundColor Green
    } else {
        Write-Host "  FAILED: BestCam NOT found in camera list" -ForegroundColor Red
        Write-Host "  Check the BestCamHost console window for errors" -ForegroundColor Red
    }
} catch {
    Write-Host "  ! Could not enumerate: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
Write-Host "Open Snap Camera -> Settings -> Camera -> BestCam Virtual Webcam"
Write-Host "Keep the BestCamHost console window OPEN"
Write-Host "To stop: press ENTER in the BestCamHost window"
Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
