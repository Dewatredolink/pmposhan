param(
    [string]$Python = ".\.venv-standalone\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$authorityDir = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $authorityDir "..\..")).Path

if (-not [System.IO.Path]::IsPathRooted($Python)) {
    $Python = Join-Path $repoRoot $Python.TrimStart('.','\')
}
if (-not (Test-Path $Python)) {
    throw "Standalone Python environment not found: $Python"
}
$Python = (Resolve-Path $Python).Path

$distDir = Join-Path $authorityDir "dist"
$buildDir = Join-Path $authorityDir "build"
$exe = Join-Path $distDir "PMPoshan-License-Authority.exe"
$requirements = Join-Path $authorityDir "requirements-desktop.txt"
$spec = Join-Path $authorityDir "license_authority.spec"

function Remove-WithRetry([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    for ($i = 0; $i -lt 20; $i++) {
        try {
            Remove-Item -Recurse -Force $Path -ErrorAction Stop
            return
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    throw "Unable to remove locked build path: $Path"
}

# Stop only a previously built copy from this exact dist directory.
Get-CimInstance Win32_Process -Filter "Name='PMPoshan-License-Authority.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -and (([System.IO.Path]::GetFullPath($_.ExecutablePath)) -eq ([System.IO.Path]::GetFullPath($exe))) } |
    ForEach-Object {
        Write-Host "Stopping stale License Authority build PID=$($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Push-Location $repoRoot
try {
    & $Python -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "License Authority dependency install failed" }

    Remove-WithRetry $buildDir
    Remove-WithRetry $distDir

    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $distDir `
        --workpath $buildDir `
        $spec
    if ($LASTEXITCODE -ne 0) { throw "License Authority desktop build failed" }

    if (-not (Test-Path $exe)) {
        throw "License Authority executable was not created: $exe"
    }

    $keyFile = "C:\PMPoshan-License-Authority\PRIVATE_KEY_B64.txt"
    if (Test-Path $keyFile) {
        $p = Start-Process -FilePath $exe -ArgumentList "--self-test" -PassThru -Wait
        if ($p.ExitCode -ne 0) { throw "Built License Authority self-test failed with exit code $($p.ExitCode)" }
        Write-Host "LICENSE_AUTHORITY_SELF_TEST=PASS"
    }
    else {
        Write-Warning "Private signing key not present on this computer; executable was built but signing-key self-test was skipped."
    }

    Write-Host "LICENSE_AUTHORITY_BUILD_OK=$exe"
}
finally {
    Pop-Location
}
