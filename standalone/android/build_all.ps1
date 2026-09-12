$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$PmApp = Join-Path $RepoRoot 'frontend'
$AuthorityApp = Join-Path $RepoRoot 'standalone\android\license_authority'

function Require-Command([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Required command not found: $Name" }
    Write-Host "$Name = $($cmd.Source)"
}

Write-Host '=== PM POSHAN Android preflight ==='
Require-Command 'node.exe'
Require-Command 'npm.cmd'
Require-Command 'java.exe'

Write-Host "Repo = $RepoRoot"
Write-Host "JAVA_HOME = $env:JAVA_HOME"
Write-Host "ANDROID_HOME = $env:ANDROID_HOME"

Write-Host "`n=== Preparing PM POSHAN Android app ==="
Push-Location $PmApp
try {
    npm.cmd install
    npm.cmd run build:android
    if (-not (Test-Path (Join-Path $PmApp 'android'))) {
        npx.cmd cap add android
    }
    npx.cmd cap sync android
}
finally {
    Pop-Location
}

Write-Host "`n=== Preparing PM POSHAN License Authority Android app ==="
Push-Location $AuthorityApp
try {
    npm.cmd install
    npm.cmd run build
    if (-not (Test-Path (Join-Path $AuthorityApp 'android'))) {
        npx.cmd cap add android
    }
    npx.cmd cap sync android
}
finally {
    Pop-Location
}

Write-Host "`nANDROID_PREPARE_OK"
Write-Host "PM_POSHAN_ANDROID = $PmApp\android"
Write-Host "LICENSE_AUTHORITY_ANDROID = $AuthorityApp\android"
Write-Host 'Open PM POSHAN: cd frontend; npx.cmd cap open android'
Write-Host 'Open License Authority: cd standalone\android\license_authority; npx.cmd cap open android'
