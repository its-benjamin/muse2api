@echo off
rem muse2api Windows launcher: double-click to install deps and start locally. No server needed.
chcp 65001 >nul
cd /d "%~dp0"

rem Refuse to run elevated: Chrome re-spawns de-elevated and the debug port
rem never opens, so every generation would time out. Right-click run WITHOUT admin.
net session >nul 2>nul
if not errorlevel 1 (
  echo [ERROR] This script is running as Administrator.
  echo [ERROR] Chrome cannot stay attached to an elevated process: every request would fail.
  echo [ERROR] Please re-run WITHOUT "Run as administrator" (plain double-click).
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo [INFO] Created .env from .env.example. Edit MUSE2API_KEY if you want your own key.
)

echo [INFO] Installing dependencies (first run takes a while)...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed. Check your network and retry.
  pause
  exit /b 1
)

if "%MUSE2API_HOST%"=="" set MUSE2API_HOST=127.0.0.1
if "%MUSE2API_PORT%"=="" set MUSE2API_PORT=18610

rem Read MUSE2API_KEY from .env so the admin URL is correct
set MUSE2API_KEY=
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  if /i "%%A"=="MUSE2API_KEY" set MUSE2API_KEY=%%B
)

echo.
echo [INFO] Starting muse2api at http://%MUSE2API_HOST%:%MUSE2API_PORT% ...
if "%MUSE2API_KEY%"=="" (
  echo [INFO] Admin panel: http://%MUSE2API_HOST%:%MUSE2API_PORT%/  ^(key will be auto-generated and printed below as "m2a_..."^)
) else (
  echo [INFO] Admin panel: http://%MUSE2API_HOST%:%MUSE2API_PORT%/?key=%MUSE2API_KEY%
)
echo [INFO] Chrome / Edge on this PC is auto-detected; MUSE2API_CHROMIUM in .env can stay empty.
echo [INFO] Keep this window open. Press Ctrl+C to stop.
echo.
python run.py
pause
