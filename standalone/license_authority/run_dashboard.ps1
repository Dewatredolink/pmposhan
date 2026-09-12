param(
    [string]$Python = ".\.venv-standalone\Scripts\python.exe",
    [int]$Port = 8775
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if (-not (Test-Path $Python)) {
    $candidate = Join-Path $repoRoot ".venv-standalone\Scripts\python.exe"
    if (Test-Path $candidate) { $Python = $candidate }
}
if (-not (Test-Path $Python)) {
    throw "Standalone Python environment not found. Expected .venv-standalone\Scripts\python.exe"
}

$keyFile = "C:\PMPoshan-License-Authority\PRIVATE_KEY_B64.txt"
if (-not (Test-Path $keyFile)) {
    throw "Private signing key not found at $keyFile"
}

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "LICENSE_AUTHORITY_ALREADY_RUNNING=http://127.0.0.1:$Port"
    Start-Process "http://127.0.0.1:$Port"
    exit 0
}

$script = Join-Path $PSScriptRoot "dashboard.py"
$env:PMPOSHAN_LICENSE_PRIVATE_KEY_FILE = $keyFile

$process = Start-Process -FilePath $Python -ArgumentList @($script) -WorkingDirectory $repoRoot -PassThru -WindowStyle Minimized
Start-Sleep -Seconds 2

if ($process.HasExited) {
    throw "License Authority Dashboard failed to start."
}

Write-Host "LICENSE_AUTHORITY_PID=$($process.Id)"
Write-Host "LICENSE_AUTHORITY_URL=http://127.0.0.1:$Port"
Start-Process "http://127.0.0.1:$Port"
