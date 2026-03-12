#!/bin/bash
# ─────────────────────────────────────────
#  START EVERYTHING — Agent + Dashboard
#  Run this from the project root:
#  bash start.sh
# ─────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     TWITTER AGENT — STARTING        ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Require a foreground TTY so logs are visible in real time.
# Allow background launch when explicitly opted-in (used by the macOS app).
if [ ! -t 1 ] && [ "${ALLOW_BACKGROUND:-}" != "1" ]; then
  echo "Please run this in the foreground to see live output."
  echo "Example: bash start.sh"
  exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Start Flask API in background
API_PORT="${DASHBOARD_API_PORT:-5001}"
echo "🖥  Starting dashboard API (port ${API_PORT})..."
DASHBOARD_API_PORT="${API_PORT}" python dashboard/server.py &
FLASK_PID=$!
echo "   API running (PID: $FLASK_PID)"

# Wait a moment for Flask to start
sleep 2

# Start React dashboard in background
echo "🎨 Starting dashboard UI (port 3000)..."
npm --prefix dashboard start &
REACT_PID=$!
echo "   UI running (PID: $REACT_PID)"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  Dashboard: http://localhost:3000   ║"
echo "║  API:       http://localhost:${API_PORT}   ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Starting agent in 3 seconds..."
sleep 3

# Start the main agent (foreground — Ctrl+C to stop everything)
python main.py

# Cleanup on exit
echo ""
echo "Stopping all processes..."
kill $FLASK_PID $REACT_PID 2>/dev/null
echo "✅ Everything stopped."
