#!/bin/bash
# ─────────────────────────────────────────
#  TWITTER AGENT — SETUP SCRIPT
#  Run this ONCE to install everything.
#  Usage: bash setup.sh
# ─────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     TWITTER AGENT — SETUP           ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. CHECK PYTHON ──────────────────────
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "❌  Python 3 not found."
    echo ""
    echo "    Download it from: https://python.org/downloads"
    echo "    (click the big yellow Download button)"
    echo ""
    echo "    ⚠️  Windows: check 'Add Python to PATH' during install!"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
    echo "❌  Python 3.9 or newer is required. You have $PY_VER"
    echo "    Download the latest from: https://python.org/downloads"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi
echo "✅  Python $PY_VER found"

# ── 2. PYTHON VIRTUAL ENVIRONMENT ────────
echo ""
echo "📦  Creating Python virtual environment..."
# Remove any existing venv — paths are machine-specific and cannot be reused
if [ -d "venv" ]; then
    rm -rf venv
fi
$PYTHON -m venv venv
if [ $? -ne 0 ]; then
    echo "❌  Failed to create virtual environment."
    echo "    Try running: $PYTHON -m pip install virtualenv"
    read -p "Press Enter to close..."
    exit 1
fi

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    source venv/Scripts/activate
fi

# ── 3. PYTHON PACKAGES ───────────────────
echo ""
echo "📦  Installing Python packages (1-2 minutes)..."
pip install --upgrade pip --quiet
# Install greenlet from pre-built wheel first — avoids C++ compile failure on some Macs
pip install --only-binary=:all: greenlet --quiet 2>/dev/null || pip install greenlet --quiet
pip install -r requirements.txt --quiet
if [ $? -ne 0 ]; then
    echo "❌  Failed to install Python packages."
    echo "    Check your internet connection and try again."
    read -p "Press Enter to close..."
    exit 1
fi
echo "✅  Python packages installed"

# ── 4. CHECK GOOGLE CHROME ───────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
    if [ ! -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
        echo ""
        echo "⚠️  Google Chrome not found."
        echo ""
        echo "    The agent uses your real Chrome browser to control Twitter."
        echo "    Please install Google Chrome first:"
        echo ""
        echo "    → https://www.google.com/chrome"
        echo ""
        echo "    After installing Chrome, run this setup again."
        echo ""
        read -p "Press Enter to close..."
        exit 1
    fi
    echo "✅  Google Chrome found"
fi

# ── 5. PLAYWRIGHT BROWSER DEPS ───────────
# channel="chrome" uses the user's real system Chrome — no separate download needed.
# We only install Playwright's OS-level dependencies (codecs, fonts, etc.)
echo ""
echo "🌐  Installing browser dependencies..."
python -m playwright install-deps chromium --quiet 2>/dev/null || true
echo "✅  Browser dependencies ready"

# ── 6. DASHBOARD BUILD ────────────────────
# If the pre-built dashboard is already included (shipped with the product),
# skip Node.js entirely. Node.js is only needed to rebuild from source.
if [ -f "dashboard/build/index.html" ]; then
    echo ""
    echo "✅  Dashboard already built — no Node.js needed"
else
    echo ""
    echo "🎨  Dashboard not pre-built — building it now..."
    echo "    (Node.js required for this step)"
    echo ""

    if ! command -v node &> /dev/null; then
        echo "❌  Node.js not found."
        echo ""
        echo "    Download it from: https://nodejs.org  (click the LTS button)"
        echo "    After installing, close this window and run setup again."
        echo ""
        read -p "Press Enter to close..."
        exit 1
    fi
    echo "✅  Node.js $(node -v) found"

    echo ""
    echo "📦  Installing dashboard dependencies..."
    npm --prefix dashboard install --silent
    if [ $? -ne 0 ]; then
        echo "❌  npm install failed. Check your internet connection."
        read -p "Press Enter to close..."
        exit 1
    fi

    echo ""
    echo "🔨  Building dashboard UI (~30 seconds)..."
    npm --prefix dashboard run build
    if [ $? -ne 0 ]; then
        echo "❌  Dashboard build failed."
        read -p "Press Enter to close..."
        exit 1
    fi
    echo "✅  Dashboard built"
fi

# ── 7. CREATE .env IF MISSING ─────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "📄  Created .env config file"
fi

# ── 8. DATA DIRECTORY ─────────────────────
mkdir -p data/chrome_profile

# ── 9. FIX PERMISSIONS (Mac) ──────────────
chmod +x setup.sh start.sh "2. Setup.command" "3. Start.command" "4. Run Agent.app/Contents/MacOS/Run Agent" 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════╗"
echo "║        SETUP COMPLETE! ✅           ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  ➜  Double-click  3. Start.command  to launch"
echo "     (or run: bash start.sh)"
echo ""
echo "  ➜  Dashboard opens at http://localhost:5001"
echo "     Go to SETTINGS → ACCOUNT & API KEYS"
echo "     and paste your Anthropic or OpenAI key."
echo ""
