@echo off
REM ─────────────────────────────────────────
REM  TWITTER AGENT — WINDOWS SETUP
REM  Double-click this file to install everything.
REM  You only need to do this ONCE.
REM ─────────────────────────────────────────

cd /d "%~dp0"
title Twitter Agent - Setup

echo.
echo ╔══════════════════════════════════════╗
echo ║     TWITTER AGENT — SETUP           ║
echo ╚══════════════════════════════════════╝
echo.

REM ── CHECK PYTHON ──────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌  Python not found.
    echo.
    echo     Download it from: https://python.org/downloads
    echo     ^(click the big yellow Download button^)
    echo.
    echo     ⚠️  IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo ✅  Python %PY_VER% found

REM ── CREATE VIRTUAL ENVIRONMENT ────────
echo.
echo 📦  Creating Python virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ❌  Failed to create virtual environment.
    echo     Try: python -m pip install virtualenv
    pause
    exit /b 1
)

REM ── INSTALL PYTHON PACKAGES ───────────
echo.
echo 📦  Installing Python packages (1-2 minutes)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ❌  Failed to install Python packages.
    echo     Check your internet connection and try again.
    pause
    exit /b 1
)
echo ✅  Python packages installed

REM ── INSTALL PLAYWRIGHT BROWSER ────────
echo.
echo 🌐  Installing automation browser (1-3 minutes)...
playwright install chromium
if errorlevel 1 (
    echo ❌  Failed to install the automation browser.
    echo     Check your internet connection and try again.
    pause
    exit /b 1
)
echo ✅  Browser installed

REM ── DASHBOARD BUILD ───────────────────
REM If the pre-built dashboard is included (shipped with the product),
REM skip Node.js entirely. Node.js is only needed to rebuild from source.
if exist "dashboard\build\index.html" (
    echo.
    echo ✅  Dashboard already built — no Node.js needed
    goto :skip_node
)

echo.
echo 🎨  Dashboard not pre-built — building it now...
echo     ^(Node.js required for this step^)
echo.

node --version >nul 2>&1
if errorlevel 1 (
    echo ❌  Node.js not found.
    echo.
    echo     Download it from: https://nodejs.org  ^(click the LTS button^)
    echo     After installing, close this window and run setup.bat again.
    echo.
    pause
    exit /b 1
)
for /f %%v in ('node --version') do set NODE_VER=%%v
echo ✅  Node.js %NODE_VER% found

echo.
echo 📦  Installing dashboard dependencies...
npm --prefix dashboard install
if errorlevel 1 (
    echo ❌  npm install failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo 🔨  Building dashboard UI (~30 seconds)...
npm --prefix dashboard run build
if errorlevel 1 (
    echo ❌  Dashboard build failed.
    pause
    exit /b 1
)
echo ✅  Dashboard built

:skip_node

REM ── CREATE .env IF MISSING ─────────────
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo 📄  Created .env config file
)

REM ── DATA DIRECTORY ────────────────────
if not exist "data\chrome_profile" mkdir "data\chrome_profile"

echo.
echo ╔══════════════════════════════════════╗
echo ║        SETUP COMPLETE! ✅           ║
echo ╚══════════════════════════════════════╝
echo.
echo   ➜  Double-click  start.bat  to launch the agent
echo.
echo   ➜  Dashboard opens at http://localhost:5001
echo      Go to SETTINGS → ACCOUNT ^& API KEYS
echo      and paste your Anthropic or OpenAI key.
echo.
pause
