param(
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"
$authorityDir = $PSScriptRoot
$sourceExe = Join-Path $authorityDir "dist\PMPoshan-License-Authority.exe"
if (-not (Test-Path $sourceExe)) {
    throw "Build the desktop app first. Missing: $sourceExe"
}

$installDir = Join-Path $env:LOCALAPPDATA "Programs\PMPoshan License Authority"
$targetExe = Join-Path $installDir "PMPoshan-License-Authority.exe"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

# Close an installed copy before replacing it.
Get-CimInstance Win32_Process -Filter "Name='PMPoshan-License-Authority.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -and (([System.IO.Path]::GetFullPath($_.ExecutablePath)) -eq ([System.IO.Path]::GetFullPath($targetExe))) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Copy-Item -Force $sourceExe $targetExe

$wsh = New-Object -ComObject WScript.Shell
$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\PM POSHAN"
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
$startShortcut = $wsh.CreateShortcut((Join-Path $startMenuDir "PM POSHAN License Authority.lnk"))
$startShortcut.TargetPath = $targetExe
$startShortcut.WorkingDirectory = $installDir
$startShortcut.Description = "PM POSHAN License Authority"
$startShortcut.Save()

if (-not $NoDesktopShortcut) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $desktopShortcut = $wsh.CreateShortcut((Join-Path $desktop "PM POSHAN License Authority.lnk"))
    $desktopShortcut.TargetPath = $targetExe
    $desktopShortcut.WorkingDirectory = $installDir
    $desktopShortcut.Description = "PM POSHAN License Authority"
    $desktopShortcut.Save()
}

Write-Host "LICENSE_AUTHORITY_INSTALLED=$targetExe"
Start-Process $targetExe
