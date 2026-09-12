param(
    [string]$Python = ".\.venv-standalone\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$spec = Join-Path $PSScriptRoot "pmposhan_bridge.spec"
$dist = Join-Path $PSScriptRoot "dist"
$work = Join-Path $PSScriptRoot "build"

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}

Push-Location $repoRoot
try {
    & $Python -m pip install -r ".\standalone\windows\requirements-build.txt"
    if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed" }

    Remove-Item -Recurse -Force $dist -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue

    & $Python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work $spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    $exe = Join-Path $dist "pmposhan-bridge.exe"
    if (-not (Test-Path $exe)) { throw "Expected sidecar was not created: $exe" }

    Write-Host "SIDE_CAR_BUILD_OK=$exe"
}
finally {
    Pop-Location
}
