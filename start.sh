#!/bin/bash
# ─────────────────────────────────────────
#  TWITTER AGENT — START SCRIPT
#  Usage: bash start.sh
# ─────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     TWITTER AGENT — STARTING        ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── CHECK SETUP ──────────────────────────
if [ ! -d "venv" ]; then
    echo "❌  Setup not run yet. Please run setup first:"
    echo "    Mac:     bash setup.sh"
    echo "    Windows: double-click setup.bat"
    exit 1
fi

if [ ! -d "dashboard/build" ]; then
    echo "❌  Dashboard not built. Please run setup first:"
    echo "    bash setup.sh"
    exit 1
fi

# ── ACTIVATE VENV ────────────────────────
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    source venv/Scripts/activate
fi

# ── RESOLVE VENV PYTHON ──────────────────
# Use the venv python directly to avoid system Python (e.g. Xcode) taking priority
if [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python3"
elif [ -f "$SCRIPT_DIR/venv/Scripts/python.exe" ]; then
    PYTHON="$SCRIPT_DIR/venv/Scripts/python.exe"
else
    PYTHON="python3"
fi

# ── FIND FREE PORT (scan 5001–5100) ──────
API_PORT=$("$PYTHON" -c "
import socket, os
preferred = int(os.environ.get('DASHBOARD_API_PORT', 5001))
for p in range(preferred, preferred + 100):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        s.bind(('127.0.0.1', p))
        s.close()
        print(p)
        break
    except OSError:
        pass
" 2>/dev/null)
if [ -z "$API_PORT" ]; then
    echo "❌  No free port found in range 5001–5100."
    echo "    Close other running apps and try again."
    exit 1
fi
mkdir -p "$SCRIPT_DIR/data"
echo "$API_PORT" > "$SCRIPT_DIR/data/port.txt"   # read by X Autopilot.app & status_overlay

# Export so main.py (and status_overlay.py) inherit the correct port
export DASHBOARD_API_PORT="${API_PORT}"

# ── START FLASK (serves API + built UI) ──
echo "🖥  Starting dashboard on port ${API_PORT}..."
"$PYTHON" dashboard/server.py &
FLASK_PID=$!
echo "   Dashboard PID: $FLASK_PID"

# ── VERIFY FLASK STARTED ─────────────────
sleep 2
if ! kill -0 $FLASK_PID 2>/dev/null; then
    echo ""
    echo "❌  Dashboard server failed to start."
    echo "    Try running setup again: double-click 2. Setup.command"
    echo ""
    exit 1
fi

echo ""
echo "🌐  Opening dashboard at http://localhost:${API_PORT}"
if command -v open &> /dev/null; then
    # macOS — try Chrome/Brave/Edge in app mode (Figma-style window, no browser chrome)
    CHROME_PATHS=(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    )
    BROWSER_OPENED=false
    for CHROME_BIN in "${CHROME_PATHS[@]}"; do
        if [ -f "$CHROME_BIN" ]; then
            "$CHROME_BIN" --app="http://localhost:${API_PORT}" \
                --window-size=1280,820 \
                --window-position=100,50 2>/dev/null &
            echo $! > "$SCRIPT_DIR/data/browser_pid"
            BROWSER_OPENED=true
            break
        fi
    done
    # Fallback to default browser if no Chrome-based browser found
    if [ "$BROWSER_OPENED" = false ]; then
        echo "   (No Chrome/Brave/Edge found — opening in your default browser)"
        open "http://localhost:${API_PORT}"
    fi


elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:${API_PORT}"      # Linux
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  Dashboard: http://localhost:${API_PORT}   ║"
echo "║  Press Ctrl+C to stop everything    ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── START AGENT (foreground) ─────────────
# tee to agent.log so the dashboard log panel can read it
mkdir -p "$SCRIPT_DIR/data"
"$PYTHON" main.py 2>&1 | tee "$SCRIPT_DIR/data/agent.log"

# ── CLEANUP ON EXIT ───────────────────────
echo ""
echo "Stopping dashboard server..."
kill $FLASK_PID 2>/dev/null
# Close the app-mode browser window
if [ -f "$SCRIPT_DIR/data/browser_pid" ]; then
    kill $(cat "$SCRIPT_DIR/data/browser_pid") 2>/dev/null
    rm -f "$SCRIPT_DIR/data/browser_pid"
fi
echo "✅  Everything stopped."
