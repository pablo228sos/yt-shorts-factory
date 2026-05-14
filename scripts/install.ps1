#requires -Version 5.1
<#
.SYNOPSIS
    One-shot installer for yt-shorts-factory on Windows.
.DESCRIPTION
    Installs ffmpeg, Python 3.12 (if missing), creates a venv, installs the
    package in editable mode, and pre-downloads the default gameplay sources.

    Run from inside the cloned repo:
        PS> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
        PS> .\scripts\install.ps1
#>

[CmdletBinding()]
param(
    [switch]$SkipGameplayDownload,
    [switch]$SkipAsmrDownload,
    [switch]$SkipSfxSynthesis,
    [switch]$SkipKokoro
)

$ErrorActionPreference = 'Stop'

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-Winget([string]$Id) {
    Write-Host ">> Installing $Id via winget..." -ForegroundColor Cyan
    winget install --id $Id -e --silent `
        --accept-source-agreements --accept-package-agreements
}

# ---------- ffmpeg ----------
if (-not (Test-Command 'ffmpeg')) {
    if (-not (Test-Command 'winget')) {
        throw "winget is not available. Install ffmpeg manually from https://www.gyan.dev/ffmpeg/builds/ and add it to PATH."
    }
    Install-Winget 'Gyan.FFmpeg'
    # Refresh PATH for the current session.
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path', 'User')
}

# ---------- Python 3.12 ----------
$python = $null
foreach ($cmd in @('py -3.12', 'python3.12', 'python')) {
    try {
        $version = & cmd /c "$cmd --version 2>&1"
        if ($LASTEXITCODE -eq 0 -and $version -match 'Python 3\.1[12]') {
            $python = $cmd
            break
        }
    } catch { }
}
if (-not $python) {
    if (-not (Test-Command 'winget')) {
        throw "Need Python 3.11 or 3.12. Install from https://www.python.org/downloads/ then re-run this script."
    }
    Install-Winget 'Python.Python.3.12'
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $python = 'py -3.12'
}

Write-Host ">> Using Python: $python" -ForegroundColor Cyan

# ---------- venv ----------
if (-not (Test-Path '.venv')) {
    Write-Host ">> Creating .venv..." -ForegroundColor Cyan
    & cmd /c "$python -m venv .venv"
}

$venvPython = Join-Path (Resolve-Path '.venv') 'Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    throw "venv creation failed: $venvPython not found."
}

# ---------- pip install ----------
Write-Host ">> Installing package (with Kokoro TTS unless -SkipKokoro)..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
if ($SkipKokoro) {
    & $venvPython -m pip install -e ".[dev]"
} else {
    & $venvPython -m pip install -e ".[dev,kokoro]"
}

# ---------- Kokoro TTS model (default-on) ----------
if (-not $SkipKokoro) {
    Write-Host ">> Downloading Kokoro model (~310 MB, one-time)..." -ForegroundColor Cyan
    & $venvPython -m yt_shorts_factory.cli download-tts-models
}

# ---------- synthesize SFX library ----------
if (-not $SkipSfxSynthesis) {
    Write-Host ">> Synthesizing default SFX library (vine boom / ding / whoosh / suspense)..." -ForegroundColor Cyan
    & $venvPython -m yt_shorts_factory.cli synthesize-sfx
}

# ---------- pre-cache gameplay ----------
if (-not $SkipGameplayDownload) {
    Write-Host ">> Pre-downloading default gameplay sources (~5-10 GB, this can take a while)..." -ForegroundColor Cyan
    & $venvPython -m yt_shorts_factory.cli download-gameplay --kind gameplay
}

# ---------- pre-cache ASMR overlay sources ----------
if (-not $SkipAsmrDownload) {
    Write-Host ">> Pre-downloading ASMR/cooking overlay sources..." -ForegroundColor Cyan
    & $venvPython -m yt_shorts_factory.cli download-gameplay --kind asmr
}

Write-Host ""
Write-Host ">> Done!" -ForegroundColor Green
Write-Host ""
Write-Host "Render your first Short (one command):" -ForegroundColor Cyan
Write-Host "    .venv\Scripts\yt-shorts-factory.exe generate-cmd --subreddit AmItheAsshole -v"
Write-Host ""
Write-Host "Or non-stop batch (rotates subs + B-roll, dedups):" -ForegroundColor Cyan
Write-Host "    .venv\Scripts\yt-shorts-factory.exe batch --count 10 -v"
Write-Host ""
Write-Host "Activate the venv to drop the .venv\Scripts\ prefix:" -ForegroundColor DarkGray
Write-Host "  cmd.exe       :   .venv\Scripts\activate.bat"
Write-Host "  PowerShell    :   .\.venv\Scripts\Activate.ps1"
