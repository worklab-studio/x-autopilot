@echo off
REM ─────────────────────────────────────────
REM  TWITTER AGENT — WINDOWS LAUNCHER
REM  Double-click this file every time you
REM  want to run the agent.
REM ─────────────────────────────────────────

cd /d "%~dp0"
title Twitter Agent

REM ── CHECK SETUP ───────────────────────
if not exist "venv" (
    echo ❌  Setup not run yet. Please double-click setup.bat first.
    pause
    exit /b 1
)

if not exist "dashboard\build" (
    echo ❌  Dashboard not built. Please double-click setup.bat first.
    pause
    exit /b 1
)

REM ── ACTIVATE VENV ─────────────────────
call venv\Scripts\activate.bat

echo.
echo ╔══════════════════════════════════════╗
echo ║     TWITTER AGENT — STARTING        ║
echo ╚══════════════════════════════════════╝
echo.

REM ── FIND FREE PORT (scan 5001–5100) ──
set API_PORT=5001
:find_port
netstat -an 2>nul | find ":%API_PORT% " | find "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    set /a API_PORT+=1
    if %API_PORT% GTR 5100 (
        echo ❌  No free port found in range 5001-5100. Close other apps and retry.
        pause
        exit /b 1
    )
    goto find_port
)
echo %API_PORT% > "%~dp0data\port.txt"

REM ── START FLASK IN A SEPARATE WINDOW ──
echo 🖥  Starting dashboard on port %API_PORT%...
start "Twitter Agent Dashboard" /min cmd /c "set DASHBOARD_API_PORT=%API_PORT% && python dashboard\server.py"

REM ── WAIT THEN OPEN BROWSER ────────────
timeout /t 3 /nobreak >nul
echo 🌐  Opening dashboard...
start http://localhost:%API_PORT%

echo.
echo ╔══════════════════════════════════════╗
echo ║  Dashboard: http://localhost:%API_PORT%   ║
echo ║  Close this window to stop agent   ║
echo ╚══════════════════════════════════════╝
echo.

REM ── START AGENT (foreground) ──────────
python main.py

echo.
echo ✅  Agent stopped. Closing dashboard...
REM Kill the dashboard server window
taskkill /fi "WindowTitle eq Twitter Agent Dashboard" /f >nul 2>&1

pause
