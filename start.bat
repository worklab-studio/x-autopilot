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

REM ── START FLASK IN A SEPARATE WINDOW ──
echo 🖥  Starting dashboard on port 5001...
start "Twitter Agent Dashboard" /min python dashboard\server.py

REM ── WAIT THEN OPEN BROWSER ────────────
timeout /t 3 /nobreak >nul
echo 🌐  Opening dashboard...
start http://localhost:5001

echo.
echo ╔══════════════════════════════════════╗
echo ║  Dashboard: http://localhost:5001   ║
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
