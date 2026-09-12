$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$PmApp = Join-Path $RepoRoot 'frontend'
$AuthorityApp = Join-Path $RepoRoot 'standalone\android\license_authority'

function Require-Command([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Required command not found: $Name" }
    Write-Host "$Name = $($cmd.Source)"
}

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    Write-Host ">> $Exe $($Arguments -join ' ')"
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Exe failed with exit code $LASTEXITCODE"
    }
}

function Assert-WebBuild([string]$AppDir) {
    $index = Join-Path $AppDir 'dist\index.html'
    if (-not (Test-Path $index)) {
        throw "Web build output missing: $index"
    }
}

Write-Host '=== PM POSHAN Android preflight ==='
Require-Command 'node.exe'
Require-Command 'npm.cmd'
Require-Command 'npx.cmd'
Require-Command 'java.exe'

if (-not $env:JAVA_HOME) { throw 'JAVA_HOME is not configured' }
if (-not $env:ANDROID_HOME) { throw 'ANDROID_HOME is not configured' }
if (-not (Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe'))) { throw "JAVA_HOME is invalid: $env:JAVA_HOME" }
if (-not (Test-Path $env:ANDROID_HOME)) { throw "ANDROID_HOME is invalid: $env:ANDROID_HOME" }

Write-Host "Repo = $RepoRoot"
Write-Host "JAVA_HOME = $env:JAVA_HOME"
Write-Host "ANDROID_HOME = $env:ANDROID_HOME"

Write-Host "`n=== Preparing PM POSHAN Android app ==="
Push-Location $PmApp
try {
    Remove-Item (Join-Path $PmApp 'dist') -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-Checked 'npm.cmd' @('install')
    Invoke-Checked 'npm.cmd' @('run', 'build:android')
    Assert-WebBuild $PmApp
    if (-not (Test-Path (Join-Path $PmApp 'android'))) {
        Invoke-Checked 'npx.cmd' @('cap', 'add', 'android')
    }
    Invoke-Checked 'npx.cmd' @('cap', 'sync', 'android')
}
finally {
    Pop-Location
}

Write-Host "`n=== Preparing PM POSHAN License Authority Android app ==="
Push-Location $AuthorityApp
try {
    Remove-Item (Join-Path $AuthorityApp 'dist') -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-Checked 'npm.cmd' @('install')
    Invoke-Checked 'npm.cmd' @('run', 'build')
    Assert-WebBuild $AuthorityApp
    if (-not (Test-Path (Join-Path $AuthorityApp 'android'))) {
        Invoke-Checked 'npx.cmd' @('cap', 'add', 'android')
    }
    Invoke-Checked 'npx.cmd' @('cap', 'sync', 'android')
}
finally {
    Pop-Location
}

Write-Host "`nANDROID_PREPARE_OK"
Write-Host "PM_POSHAN_ANDROID = $PmApp\android"
Write-Host "LICENSE_AUTHORITY_ANDROID = $AuthorityApp\android"
Write-Host 'Open PM POSHAN: cd frontend; npx.cmd cap open android'
Write-Host 'Open License Authority: cd standalone\android\license_authority; npx.cmd cap open android'
