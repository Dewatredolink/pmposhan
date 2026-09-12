param(
    [string]$Python = ".\.venv-standalone\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$frontend = Join-Path $repoRoot "frontend"
$tauriDir = Join-Path $frontend "src-tauri"
$binDir = Join-Path $tauriDir "binaries"
$sidecarSource = Join-Path $PSScriptRoot "dist\pmposhan-bridge.exe"
$sidecarTarget = Join-Path $binDir "pmposhan-bridge-x86_64-pc-windows-msvc.exe"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Require-Command "node"
Require-Command "npm"
Require-Command "cargo"
Require-Command "rustc"

Push-Location $repoRoot
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\standalone\windows\build_sidecar.ps1" -Python $Python
    if ($LASTEXITCODE -ne 0) { throw "Sidecar build failed" }

    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    Copy-Item -Force $sidecarSource $sidecarTarget
    if (-not (Test-Path $sidecarTarget)) { throw "Tauri sidecar copy failed: $sidecarTarget" }

    Push-Location $frontend
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

        & npm run tauri build
        if ($LASTEXITCODE -ne 0) { throw "Tauri build failed" }
    }
    finally {
        Pop-Location
    }

    $bundleDir = Join-Path $tauriDir "target\release\bundle\nsis"
    if (-not (Test-Path $bundleDir)) { throw "NSIS bundle directory not found: $bundleDir" }
    $installer = Get-ChildItem $bundleDir -Filter "*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $installer) { throw "NSIS installer was not created" }

    Write-Host "TAURI_BUILD_OK=$($installer.FullName)"
}
finally {
    Pop-Location
}
