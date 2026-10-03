# muse2api Windows launcher (PowerShell). Double-click or: powershell -ExecutionPolicy Bypass -File start-windows.ps1
# No server needed: installs deps and starts the API on this machine.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# Refuse to run elevated: Chrome re-spawns de-elevated and the debug port
# never opens, so every generation would time out. Re-run WITHOUT admin.
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
  Write-Host '[ERROR] This script is running as Administrator.' -ForegroundColor Red
  Write-Host '[ERROR] Chrome cannot stay attached to an elevated process: every request would fail.' -ForegroundColor Red
  Write-Host '[ERROR] Please re-run WITHOUT "Run as administrator" (plain double-click).' -ForegroundColor Red
  Read-Host 'Press Enter to exit'
  exit 1
}

try { $null = Get-Command python -ErrorAction Stop } catch {
  Write-Host '[ERROR] Python not found. Install Python 3.10+ from https://www.python.org/downloads/ and tick "Add python.exe to PATH".' -ForegroundColor Red
  Read-Host 'Press Enter to exit'
  exit 1
}

if (-not (Test-Path '.env')) {
  Copy-Item '.env.example' '.env'
  Write-Host '[INFO] Created .env from .env.example. Edit MUSE2API_KEY if you want your own key.'
}

Write-Host '[INFO] Installing dependencies (first run takes a while)...'
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
  Write-Host '[ERROR] pip install failed. Check your network and retry.' -ForegroundColor Red
  Read-Host 'Press Enter to exit'
  exit 1
}

if (-not $env:MUSE2API_HOST) { $env:MUSE2API_HOST = '127.0.0.1' }
if (-not $env:MUSE2API_PORT) { $env:MUSE2API_PORT = '18610' }

# Read MUSE2API_KEY from .env so the admin URL is correct
$envKey = ''
if (Test-Path '.env') {
  foreach ($line in Get-Content '.env') {
    if ($line -match '^MUSE2API_KEY\s*=\s*(.+)$') { $envKey = $Matches[1].Trim(); break }
  }
}

Write-Host ''
Write-Host "[INFO] Starting muse2api at http://$($env:MUSE2API_HOST):$($env:MUSE2API_PORT) ..."
if ($envKey) {
  Write-Host "[INFO] Admin panel: http://$($env:MUSE2API_HOST):$($env:MUSE2API_PORT)/?key=$envKey"
} else {
  Write-Host "[INFO] Admin panel: http://$($env:MUSE2API_HOST):$($env:MUSE2API_PORT)/  (key will be auto-generated and printed below as 'm2a_...')"
}
Write-Host '[INFO] Chrome / Edge on this PC is auto-detected; MUSE2API_CHROMIUM in .env can stay empty.'
Write-Host '[INFO] Keep this window open. Press Ctrl+C to stop.'
Write-Host ''
python run.py
