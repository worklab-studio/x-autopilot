#!/bin/bash
# ─────────────────────────────────────────
#  TWITTER AGENT — MAC SETUP
#  Double-click this file to install everything.
#  You only need to do this ONCE.
#
#  If macOS says "cannot be opened":
#  → Right-click the file → Open → Open
# ─────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Fix permissions on all runnable files so future double-clicks work
chmod +x setup.sh start.sh setup.command start.command 2>/dev/null
chmod +x "twitter agent.command" 2>/dev/null

bash setup.sh

echo ""
echo "Press Enter to close this window..."
read
