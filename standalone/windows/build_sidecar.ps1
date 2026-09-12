param(
    [string]$Python = ".\.venv-standalone\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$spec = Join-Path $PSScriptRoot "pmposhan_bridge.spec"
$dist = Join-Path $PSScriptRoot "dist"
$work = Join-Path $PSScriptRoot "build"
$exe = Join-Path $dist "pmposhan-bridge.exe"

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}

function Stop-ExistingSidecar {
    param([string]$TargetExe)

    $targetFull = [System.IO.Path]::GetFullPath($TargetExe)
    $matched = @()

    foreach ($p in @(Get-Process -Name "pmposhan-bridge" -ErrorAction SilentlyContinue)) {
        try {
            if ($p.Path -and ([System.IO.Path]::GetFullPath($p.Path) -ieq $targetFull)) {
                $matched += $p
            }
        }
        catch {
            # Ignore processes whose executable path cannot be inspected.
        }
    }

    foreach ($p in $matched) {
        Write-Host "Stopping existing sidecar process PID=$($p.Id) before rebuild..."
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        try { Wait-Process -Id $p.Id -Timeout 5 -ErrorAction SilentlyContinue } catch {}
    }
}

function Remove-PathWithRetry {
    param([string]$Path)

    if (-not (Test-Path $Path)) { return }

    $lastError = $null
    for ($i = 0; $i -lt 20; $i++) {
        try {
            Remove-Item -Recurse -Force $Path -ErrorAction Stop
            return
        }
        catch {
            $lastError = $_
            Start-Sleep -Milliseconds 250
        }
    }
    throw "Could not remove build path after retries: $Path`n$lastError"
}

Push-Location $repoRoot
try {
    & $Python -m pip install -r ".\standalone\windows\requirements-build.txt"
    if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed" }

    # A previously launched smoke-test or sidecar instance can keep the EXE
    # locked on Windows. Stop only a process whose executable path matches the
    # exact dist binary, then retry removal until Windows releases the handle.
    Stop-ExistingSidecar -TargetExe $exe
    Remove-PathWithRetry -Path $dist
    Remove-PathWithRetry -Path $work

    & $Python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work $spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    if (-not (Test-Path $exe)) { throw "Expected sidecar was not created: $exe" }

    Write-Host "SIDE_CAR_BUILD_OK=$exe"
}
finally {
    Pop-Location
}
