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
$iconSource = Join-Path $frontend "public\icons\icon-512.png"
$iconTarget = Join-Path $tauriDir "icons\icon.ico"

function Resolve-CommandPath([string]$Name, [string[]]$Fallbacks = @()) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in $Fallbacks) {
        if ($candidate -and (Test-Path $candidate)) { return (Resolve-Path $candidate).Path }
    }
    return $null
}

function Import-VsDevEnvironment {
    if (Get-Command link.exe -ErrorAction SilentlyContinue) {
        Write-Host "MSVC_LINK_READY=$((Get-Command link.exe).Source)"
        return
    }

    $vswhereCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"),
        (Join-Path $env:ProgramFiles "Microsoft Visual Studio\Installer\vswhere.exe")
    ) | Where-Object { $_ -and (Test-Path $_) }

    $vswhere = $vswhereCandidates | Select-Object -First 1
    if (-not $vswhere) {
        throw "MSVC linker (link.exe) not found. Install Visual Studio Build Tools with the Desktop development with C++ workload, then rerun this script. Suggested command: winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override `"--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended`""
    }

    $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $installPath) {
        throw "Visual Studio Build Tools are present, but the MSVC C++ toolchain is missing. Open Visual Studio Installer and add 'Desktop development with C++', including MSVC x64/x86 build tools and a Windows 10/11 SDK."
    }

    $vcvars = Join-Path $installPath "VC\Auxiliary\Build\vcvars64.bat"
    if (-not (Test-Path $vcvars)) {
        throw "MSVC environment script not found: $vcvars"
    }

    Write-Host "Loading MSVC environment from $vcvars"
    $envLines = & cmd.exe /d /s /c "`"$vcvars`" >nul && set"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to initialize the Visual C++ build environment using vcvars64.bat"
    }
    foreach ($line in $envLines) {
        $idx = $line.IndexOf('=')
        if ($idx -gt 0) {
            $name = $line.Substring(0, $idx)
            $value = $line.Substring($idx + 1)
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }

    $link = Get-Command link.exe -ErrorAction SilentlyContinue
    if (-not $link) {
        throw "Visual C++ environment loaded, but link.exe is still unavailable. Verify MSVC x64/x86 build tools and Windows SDK are installed."
    }
    Write-Host "MSVC_LINK_READY=$($link.Source)"
}

$node = Resolve-CommandPath "node.exe"
$npm = Resolve-CommandPath "npm.cmd" @("C:\Program Files\nodejs\npm.cmd")
$cargoFallback = Join-Path $env:USERPROFILE ".cargo\bin\cargo.exe"
$rustcFallback = Join-Path $env:USERPROFILE ".cargo\bin\rustc.exe"
$cargo = Resolve-CommandPath "cargo.exe" @($cargoFallback)
$rustc = Resolve-CommandPath "rustc.exe" @($rustcFallback)

if (-not $node) { throw "Required command not found: node.exe" }
if (-not $npm) { throw "Required command not found: npm.cmd" }
if (-not $cargo -or -not $rustc) {
    throw "Rust toolchain not found. Install Rustup first (for example: winget install --id Rustlang.Rustup -e), then open a new PowerShell window and rerun this script."
}

$cargoDir = Split-Path -Parent $cargo
if (-not (($env:PATH -split ';') -contains $cargoDir)) {
    $env:PATH = "$cargoDir;$env:PATH"
}

Write-Host "NODE=$node"
Write-Host "NPM=$npm"
Write-Host "CARGO=$cargo"
Write-Host "RUSTC=$rustc"
Write-Host "RUST_PATH_READY=$cargoDir"

& $cargo --version
if ($LASTEXITCODE -ne 0) { throw "cargo exists but could not run" }
& $rustc --version
if ($LASTEXITCODE -ne 0) { throw "rustc exists but could not run" }

Import-VsDevEnvironment

Push-Location $repoRoot
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\standalone\windows\build_sidecar.ps1" -Python $Python
    if ($LASTEXITCODE -ne 0) { throw "Sidecar build failed" }

    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    Copy-Item -Force $sidecarSource $sidecarTarget
    if (-not (Test-Path $sidecarTarget)) { throw "Tauri sidecar copy failed: $sidecarTarget" }

    Push-Location $frontend
    try {
        & $npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

        if (-not (Test-Path $iconSource)) {
            throw "Tauri icon source not found: $iconSource"
        }
        if (-not (Test-Path $iconTarget)) {
            Write-Host "Generating Tauri desktop icons from $iconSource"
            & $npm run tauri -- icon ".\public\icons\icon-512.png"
            if ($LASTEXITCODE -ne 0) { throw "Tauri icon generation failed" }
        }
        if (-not (Test-Path $iconTarget)) {
            throw "Tauri icon generation completed but icon.ico is still missing: $iconTarget"
        }
        Write-Host "TAURI_ICON_READY=$iconTarget"

        & $npm run tauri build
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
