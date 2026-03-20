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
chmod +x setup.sh start.sh "2. Setup.command" "3. Start.command" 2>/dev/null

# Strip macOS quarantine from all runnable files so everything can be double-clicked
# without Gatekeeper warnings after this one-time setup run
xattr -d com.apple.quarantine \
  "$SCRIPT_DIR/3. Start.command" \
  "$SCRIPT_DIR/start.sh" \
  "$SCRIPT_DIR/2. Setup.command" \
  "$SCRIPT_DIR/setup.sh" \
  2>/dev/null
# Strip quarantine from the .app bundle (recursive — covers all files inside)
xattr -dr com.apple.quarantine "$SCRIPT_DIR/4. Run Agent.app" 2>/dev/null
chmod +x "$SCRIPT_DIR/4. Run Agent.app/Contents/MacOS/Run Agent" 2>/dev/null

bash setup.sh

echo ""
echo "Press Enter to close this window..."
read
