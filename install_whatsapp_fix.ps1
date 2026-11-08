<#
.SYNOPSIS
    Installs the PixelMorph WhatsApp camera fix.
    Forces Chrome to use DirectShow instead of Media Foundation for cameras,
    so PixelMorph appears in WhatsApp's camera list.

    Run this as Administrator once after installing PixelMorph.
#>

#Requires -RunAsAdministrator

Write-Host "PixelMorph — WhatsApp Camera Fix Installer" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Set Chrome policy to disable Media Foundation Camera
Write-Host "[1/3] Setting Chrome policy to enable DirectShow cameras..." -ForegroundColor Yellow
$policyPath = "HKLM:\SOFTWARE\Policies\Google\Chrome"
if (-not (Test-Path $policyPath)) {
    New-Item -Path $policyPath -Force | Out-Null
}

# Disable MediaFoundationCamera via Chrome policy
$featureDisabled = Get-ItemProperty -Path $policyPath -Name "ForceDisabledFeatures" -ErrorAction SilentlyContinue
if ($featureDisabled) {
    $current = $featureDisabled.ForceDisabledFeatures
    if ($current -notlike "*MediaFoundationCamera*") {
        Set-ItemProperty -Path $policyPath -Name "ForceDisabledFeatures" -Value "$current,MediaFoundationCamera"
        Write-Host "  Appended MediaFoundationCamera to existing policy" -ForegroundColor Green
    } else {
        Write-Host "  Policy already set" -ForegroundColor Green
    }
} else {
    New-ItemProperty -Path $policyPath -Name "ForceDisabledFeatures" -Value "MediaFoundationCamera" -PropertyType String -Force | Out-Null
    Write-Host "  Created new policy: MediaFoundationCamera disabled" -ForegroundColor Green
}

# Step 2: Find and update WhatsApp shortcut
Write-Host "[2/3] Updating WhatsApp shortcut..." -ForegroundColor Yellow
$shortcutPaths = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Applications Chrome\WhatsApp Web.lnk",
    "$env:PUBLIC\Desktop\WhatsApp Web.lnk",
    "$env:USERPROFILE\Desktop\WhatsApp Web.lnk"
)

$updated = $false
foreach ($scPath in $shortcutPaths) {
    if (Test-Path $scPath) {
        try {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($scPath)
            $target = $shortcut.TargetPath
            $args = $shortcut.Arguments

            # Check if our flags are already there
            if ($args -notlike "*disable-features=MediaFoundationCamera*") {
                $newArgs = "$args --disable-features=MediaFoundationCamera --enable-features=WebRtcUseWinDshowCamera"
                $shortcut.Arguments = $newArgs
                $shortcut.Save()
                Write-Host "  Updated: $scPath" -ForegroundColor Green
                Write-Host "  New args: $newArgs" -ForegroundColor Gray
                $updated = $true
            } else {
                Write-Host "  Already updated: $scPath" -ForegroundColor Green
                $updated = $true
            }
        } catch {
            Write-Host "  Failed to update $scPath : $_" -ForegroundColor Red
        }
    }
}

if (-not $updated) {
    Write-Host "  No WhatsApp shortcuts found. Creating desktop shortcut..." -ForegroundColor Yellow
    $desktop = [Environment]::GetFolderPath("Desktop")
    $scPath = Join-Path $desktop "WhatsApp Web.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($scPath)
    $shortcut.TargetPath = "C:\Program Files\Google\Chrome\Application\chrome_proxy.exe"
    $shortcut.Arguments = "--profile-directory=Default --app-id=hnpfjngllnobngcgfapefoaidbinmjnm --disable-features=MediaFoundationCamera --enable-features=WebRtcUseWinDshowCamera"
    $shortcut.IconLocation = "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Web Applications\_crx_hnpfjngllnobngcgfapefoaidbinmjnm\WhatsApp Web.ico,0"
    $shortcut.Save()
    Write-Host "  Created: $scPath" -ForegroundColor Green
}

# Step 3: Create desktop shortcut for PixelMorph WhatsApp helper
Write-Host "[3/3] Creating PixelMorph WhatsApp helper shortcut..." -ForegroundColor Yellow
$batPath = Join-Path $PSScriptRoot "PixelMorph_WhatsApp.bat"
if (Test-Path $batPath) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $scPath = Join-Path $desktop "PixelMorph WhatsApp.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($scPath)
    $shortcut.TargetPath = $batPath
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Description = "Launch WhatsApp with PixelMorph camera support"
    $shortcut.Save()
    Write-Host "  Created: $scPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "✓ Fix installed!" -ForegroundColor Green
Write-Host ""
Write-Host "Usage:" -ForegroundColor Cyan
Write-Host "  1. Run PixelMorph and press START" -ForegroundColor White
Write-Host "  2. Open WhatsApp (shortcut or desktop)" -ForegroundColor White
Write-Host "  3. Go to Settings → Audio and Video" -ForegroundColor White
Write-Host "  4. Select PixelMorph as camera" -ForegroundColor White
Write-Host ""
Write-Host "NOTE: Restart Chrome completely for the policy to take effect." -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to exit"
