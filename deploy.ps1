# AegisOne deploy helper.
# Runs from C:\Code\AegisOne; assumes git remote 'origin' is already set.
# After you've done the four browser steps (create repo, deploy on Render,
# deploy on Vercel, paste keepalive URL), run this to:
#   1. Push latest code to GitHub.
#   2. Rebuild the APK with the production backend URL embedded.
#
# Usage:
#   .\deploy.ps1 -BackendUrl "https://aegisone-backend-devshah.onrender.com"
#
# Optional: skip APK rebuild if you've already done it manually.
#   .\deploy.ps1 -BackendUrl "..." -SkipApk

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackendUrl,

    [switch]$SkipApk
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Section($msg) {
    Write-Host ""
    Write-Host "=== $msg ===" -ForegroundColor Cyan
}

# 1. Push to GitHub
Write-Section "1/3 Pushing to GitHub"
$remote = git remote get-url origin 2>$null
if (-not $remote) {
    Write-Host "ERROR: no git remote 'origin' set." -ForegroundColor Red
    Write-Host "Run: git remote add origin https://github.com/DevangShah7/aegisone.git" -ForegroundColor Yellow
    exit 1
}
Write-Host "Remote: $remote" -ForegroundColor Gray
git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed. Try: git push -u origin main --force-with-lease" -ForegroundColor Red
    exit 1
}

# 2. Verify backend is reachable
Write-Section "2/3 Verifying backend health"
$healthUrl = "$BackendUrl/healthz"
Write-Host "GET $healthUrl"
try {
    $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 10
    if ($resp.StatusCode -eq 200) {
        Write-Host "OK — backend is live." -ForegroundColor Green
    } else {
        Write-Host "Backend returned $($resp.StatusCode). Continuing anyway." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Could not reach backend at $healthUrl — Render may still be building." -ForegroundColor Yellow
    Write-Host "Check the Render dashboard. Continuing with APK rebuild anyway." -ForegroundColor Yellow
}

# 3. Rebuild APK with the new backend URL
if ($SkipApk) {
    Write-Section "3/3 Skipping APK rebuild (used -SkipApk)"
    Write-Host "Done. Push + verify only." -ForegroundColor Green
    exit 0
}

Write-Section "3/3 Rebuilding APK"
$jdk = "C:\Users\DEVANG\jdk-17\jdk-17.0.20+8"
if (-not (Test-Path $jdk)) {
    # try a few common locations
    $candidates = @(
        "C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot",
        "C:\Program Files\Java\jdk-17",
        "C:\Program Files\OpenJDK\jdk-17"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $jdk = $c; break }
    }
}
if (-not (Test-Path $jdk)) {
    Write-Host "JDK 17 not found at $jdk. Set JDK_PATH env var to your JDK 17 location." -ForegroundColor Red
    exit 1
}
$env:JAVA_HOME = $jdk
$env:Path = "$jdk\bin;$env:Path"
# Note: Gradle does NOT auto-promote the AegisOneApiBaseUrl env var into a
# project property — it must be passed on the command line as -P.
Push-Location "android-agent"
try {
    & .\gradlew.bat :app:assembleDebug -PAegisOneApiBaseUrl="$BackendUrl" --console=plain
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Gradle build failed." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

$apk = "android-agent\app\build\outputs\apk\debug\app-debug.apk"
if (Test-Path $apk) {
    $size = (Get-Item $apk).Length / 1MB
    Write-Host ""
    Write-Host "APK ready:" -ForegroundColor Green
    Write-Host "  $((Resolve-Path $apk).Path)" -ForegroundColor White
    Write-Host "  Size: $([math]::Round($size, 2)) MB" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Install with: adb install -r `"$apk`"" -ForegroundColor Cyan
} else {
    Write-Host "APK not found at expected path. Check build output." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "All done. Final URLs:" -ForegroundColor Green
Write-Host "  Backend:  $BackendUrl"
Write-Host "  Dashboard: (paste from Vercel — should be https://aegisone.vercel.app or similar)"
