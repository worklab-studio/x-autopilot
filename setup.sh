#!/bin/bash
# ─────────────────────────────────────────
#  TWITTER AGENT — SETUP SCRIPT
#  Run this ONCE to install everything
#  Usage: bash setup.sh
# ─────────────────────────────────────────

set -e  # Exit on any error

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     TWITTER AGENT — SETUP           ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Install from https://python.org"
    exit 1
fi
echo "✅ Python found: $(python3 --version)"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip not found. Please install pip."
    exit 1
fi
echo "✅ pip found"

# Create virtual environment
echo ""
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo ""
echo "📦 Installing Python packages..."
pip install -r requirements.txt

# Install Playwright browsers
echo ""
echo "🌐 Installing Playwright Chrome..."
playwright install chromium
playwright install-deps chromium

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  Created .env file — IMPORTANT: Open it and add your LLM API key!"
    echo "   File location: $(pwd)/.env"
fi

# Create data directory
mkdir -p data/chrome_profile

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     SETUP COMPLETE! ✅              ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "NEXT STEPS:"
echo "1. Open .env and add one of these:"
echo "   - ANTHROPIC_API_KEY (https://console.anthropic.com)"
echo "   - OPENAI_API_KEY (https://platform.openai.com/api-keys)"
echo "   Optional: set LLM_PROVIDER=openai or anthropic (default is auto)"
echo ""
echo "2. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "3. Test your session:"
echo "   python main.py --test"
echo ""
echo "4. Start the agent:"
echo "   python main.py"
echo ""
