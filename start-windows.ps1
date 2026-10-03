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

# Load every key=value from .env into the process environment.
# This makes all MUSE2API_* settings available to Python via os.environ,
# and lets the lines below show the correct host/port/key.
foreach ($line in Get-Content '.env') {
  $line = $line.Trim()
  if ($line -eq '' -or $line.StartsWith('#')) { continue }
  $idx = $line.IndexOf('=')
  if ($idx -lt 1) { continue }
  $k = $line.Substring(0, $idx).Trim()
  $v = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
  if ($k -ne '') { [System.Environment]::SetEnvironmentVariable($k, $v, 'Process') }
}

# Fallback defaults if .env left them empty
if (-not $env:MUSE2API_HOST) { $env:MUSE2API_HOST = '127.0.0.1' }
if (-not $env:MUSE2API_PORT) { $env:MUSE2API_PORT = '18610' }

Write-Host ''
Write-Host "[INFO] Starting muse2api at http://$($env:MUSE2API_HOST):$($env:MUSE2API_PORT) ..."
if ($env:MUSE2API_KEY) {
  Write-Host "[INFO] Admin panel: http://$($env:MUSE2API_HOST):$($env:MUSE2API_PORT)/?key=$($env:MUSE2API_KEY)"
} else {
  Write-Host "[INFO] Admin panel: http://$($env:MUSE2API_HOST):$($env:MUSE2API_PORT)/  (key will be auto-generated and printed below as 'm2a_...')"
}
Write-Host '[INFO] Chrome / Edge on this PC is auto-detected; MUSE2API_CHROMIUM in .env can stay empty.'
Write-Host '[INFO] Keep this window open. Press Ctrl+C to stop.'
Write-Host ''
python run.py
