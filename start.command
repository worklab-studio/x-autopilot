#!/bin/bash
# ─────────────────────────────────────────
#  TWITTER AGENT — MAC LAUNCHER
#  Double-click this file every time you
#  want to run the agent.
# ─────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

bash start.sh
