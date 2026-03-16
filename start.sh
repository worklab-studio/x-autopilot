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

# ── START FLASK (serves API + built UI) ──
API_PORT="${DASHBOARD_API_PORT:-5001}"
echo "🖥  Starting dashboard on port ${API_PORT}..."
DASHBOARD_API_PORT="${API_PORT}" python dashboard/server.py &
FLASK_PID=$!
echo "   Dashboard PID: $FLASK_PID"

# ── WAIT THEN OPEN BROWSER ───────────────
sleep 2
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
        open "http://localhost:${API_PORT}"
    fi

    # ── Browser watcher — closing the window stops the agent ──
    # Runs in background; when browser PID disappears (Cmd+Q or red X),
    # writes quit_flag so the agent shuts down gracefully.
    if [ "$BROWSER_OPENED" = true ]; then
        (
            WATCH_PID=$(cat "$SCRIPT_DIR/data/browser_pid" 2>/dev/null)
            while [ -n "$WATCH_PID" ] && kill -0 "$WATCH_PID" 2>/dev/null; do
                sleep 1
            done
            # Only trigger if agent is still running (not already quitting)
            if [ ! -f "$SCRIPT_DIR/data/quit_flag" ]; then
                touch "$SCRIPT_DIR/data/quit_flag"
            fi
        ) &
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
python main.py

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
