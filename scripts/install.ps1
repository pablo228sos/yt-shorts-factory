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
    [switch]$SkipKokoro,
    [switch]$SkipRender,
    [string]$Subreddit = 'AmItheAsshole'
)

$ErrorActionPreference = 'Stop'

function Invoke-Tolerant([string]$Label, [scriptblock]$Action) {
    # Big media downloads regularly trip on flaky home Wi-Fi. We don't
    # want a single transient failure to abort the whole install — the
    # pipeline already degrades gracefully when caches are missing, and
    # the user can re-run the step later. Just warn and continue.
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) {
            Write-Host ("!! {0} exited with code {1}; continuing." -f $Label, $LASTEXITCODE) -ForegroundColor Yellow
        }
    } catch {
        Write-Host ("!! {0} failed: {1}. Continuing without it; re-run later when online." -f $Label, $_.Exception.Message) -ForegroundColor Yellow
    }
}

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
    Invoke-Tolerant 'Kokoro model download' { & $venvPython -m yt_shorts_factory.cli download-tts-models }
}

# ---------- synthesize SFX library ----------
if (-not $SkipSfxSynthesis) {
    Write-Host ">> Synthesizing default SFX library (vine boom / ding / whoosh / suspense)..." -ForegroundColor Cyan
    Invoke-Tolerant 'SFX synthesis' { & $venvPython -m yt_shorts_factory.cli synthesize-sfx }
}

# ---------- pre-cache gameplay ----------
if (-not $SkipGameplayDownload) {
    Write-Host ">> Pre-downloading default gameplay sources (~5-10 GB, this can take a while)..." -ForegroundColor Cyan
    Invoke-Tolerant 'Gameplay pre-cache' { & $venvPython -m yt_shorts_factory.cli download-gameplay --kind gameplay }
}

# ---------- pre-cache ASMR overlay sources ----------
if (-not $SkipAsmrDownload) {
    Write-Host ">> Pre-downloading ASMR/cooking overlay sources (~2-3 GB)..." -ForegroundColor Cyan
    Invoke-Tolerant 'ASMR pre-cache' { & $venvPython -m yt_shorts_factory.cli download-gameplay --kind asmr }
}

# ---------- smoke-test render so the user immediately has an mp4 ----------
if (-not $SkipRender) {
    Write-Host ""
    Write-Host ">> Rendering your first Short from r/$Subreddit ..." -ForegroundColor Cyan
    Invoke-Tolerant 'Smoke render' { & $venvPython -m yt_shorts_factory.cli generate-cmd --subreddit $Subreddit -v }
    if (Test-Path 'out') {
        $latest = Get-ChildItem -Path 'out' -Filter *.mp4 -ErrorAction SilentlyContinue |
                  Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latest) {
            Write-Host ""
            Write-Host (">> First Short ready: {0}" -f $latest.FullName) -ForegroundColor Green
            try { Start-Process explorer.exe ('/select,' + $latest.FullName) | Out-Null } catch {}
        }
    }
}

Write-Host ""
Write-Host ">> Done!" -ForegroundColor Green
Write-Host ""
Write-Host "Render another Short (one command):" -ForegroundColor Cyan
Write-Host "    .venv\Scripts\yt-shorts-factory.exe generate-cmd --subreddit AmItheAsshole -v"
Write-Host ""
Write-Host "Non-stop batch (rotates subs + B-roll, dedups):" -ForegroundColor Cyan
Write-Host "    .venv\Scripts\yt-shorts-factory.exe batch --count 10 -v"
Write-Host ""
Write-Host "Activate the venv to drop the .venv\Scripts\ prefix:" -ForegroundColor DarkGray
Write-Host "  cmd.exe       :   .venv\Scripts\activate.bat"
Write-Host "  PowerShell    :   .\.venv\Scripts\Activate.ps1"
