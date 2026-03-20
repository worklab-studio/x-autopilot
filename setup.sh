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

# ── 4. AUTOMATION BROWSER ────────────────
echo ""
echo "🌐  Installing automation browser (1-3 minutes)..."
# Use the user's real system Chrome — stable on all Mac hardware including ARM64
python -m playwright install chrome
if [ $? -ne 0 ]; then
    echo "❌  Failed to install the automation browser."
    echo "    Check your internet connection and try again."
    read -p "Press Enter to close..."
    exit 1
fi
echo "✅  Browser installed"

# ── 5. DASHBOARD BUILD ────────────────────
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

# ── 6. CREATE .env IF MISSING ─────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "📄  Created .env config file"
fi

# ── 7. DATA DIRECTORY ─────────────────────
mkdir -p data/chrome_profile

# ── 8. FIX PERMISSIONS (Mac) ──────────────
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
