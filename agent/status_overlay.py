"""
status_overlay.py — Floating status bar overlay for the live browser.
Includes Quit and Skip Break buttons for live control of the agent.
"""

import os
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
QUIT_FLAG_PATH = Path(__file__).parent.parent / "data" / "quit_flag"
SKIP_BREAK_FLAG_PATH = Path(__file__).parent.parent / "data" / "skip_break_flag"
_page = None


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def register_page(page):
    global _page
    _page = page


def _overlay_enabled() -> bool:
    cfg = _load_config()
    return bool(cfg.get("ui", {}).get("status_overlay_enabled", True))


# ── Quit flag ────────────────────────────────────────────
def set_quit_flag():
    QUIT_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUIT_FLAG_PATH.touch()


def clear_quit_flag():
    try:
        QUIT_FLAG_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def quit_requested() -> bool:
    return QUIT_FLAG_PATH.exists()


# ── Skip Break flag ──────────────────────────────────────
def set_skip_break_flag():
    SKIP_BREAK_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SKIP_BREAK_FLAG_PATH.touch()


def clear_skip_break_flag():
    try:
        SKIP_BREAK_FLAG_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def skip_break_requested() -> bool:
    return SKIP_BREAK_FLAG_PATH.exists()


# ── Overlay JS ───────────────────────────────────────────
_OVERLAY_JS = r"""
(statusText) => {
  const API_BASE = "http://localhost:__PORT__";
  const id = "agent-status-overlay";
  let el = document.getElementById(id);

  if (!el) {
    el = document.createElement("div");
    el.id = id;

    Object.assign(el.style, {
      position:      "fixed",
      top:           "8px",
      left:          "50%",
      transform:     "translateX(-50%)",
      zIndex:        "2147483647",
      background:    "rgba(12, 12, 12, 0.88)",
      color:         "#e6e6e6",
      border:        "1px solid rgba(255,255,255,0.18)",
      fontSize:      "12px",
      fontFamily:    "Menlo, Monaco, 'Courier New', monospace",
      padding:       "5px 8px 5px 12px",
      borderRadius:  "8px",
      boxShadow:     "0 2px 12px rgba(0,0,0,0.40)",
      display:       "flex",
      alignItems:    "center",
      gap:           "8px",
      maxWidth:      "84%",
      pointerEvents: "auto",
      userSelect:    "none",
    });

    // Status text
    const txt = document.createElement("span");
    txt.id = "agent-status-text";
    Object.assign(txt.style, {
      overflow:     "hidden",
      textOverflow: "ellipsis",
      whiteSpace:   "nowrap",
      flex:         "1",
    });
    el.appendChild(txt);

    // ── Skip Break button ──────────────────────────
    const skipBtn = document.createElement("button");
    skipBtn.id    = "agent-skip-break-btn";
    skipBtn.textContent = "⏩ Skip";
    Object.assign(skipBtn.style, {
      background:   "rgba(234, 179, 8, 0.80)",
      color:        "#000",
      border:       "none",
      borderRadius: "5px",
      fontSize:     "11px",
      fontFamily:   "inherit",
      fontWeight:   "600",
      padding:      "3px 9px",
      cursor:       "pointer",
      flexShrink:   "0",
      display:      "none",          // hidden until in a break/sleep
      transition:   "background 0.15s",
    });
    skipBtn.onmouseenter = () => skipBtn.style.background = "rgba(202,138,4,0.95)";
    skipBtn.onmouseleave = () => skipBtn.style.background = "rgba(234,179,8,0.80)";
    skipBtn.onclick = () => {
      skipBtn.textContent = "⏩ Skipping…";
      skipBtn.disabled = true;
      window.__agentSkipBreak = true;
      // POST to the API — this writes the file flag Python polls every 3 s
      fetch(API_BASE + "/api/agent/skip-break", { method: "POST" })
        .then(() => {
          // Status text will update within ~3 s when Python detects the flag
        })
        .catch(() => {});
      // Keep button disabled until status text changes (Python updates it)
      // Safety reset after 8 s in case something went wrong
      setTimeout(() => {
        skipBtn.textContent = "⏩ Skip";
        skipBtn.disabled = false;
      }, 8000);
    };
    el.appendChild(skipBtn);

    // ── Quit button ────────────────────────────────
    const quitBtn = document.createElement("button");
    quitBtn.textContent = "✕ Quit";
    Object.assign(quitBtn.style, {
      background:   "rgba(220, 38, 38, 0.85)",
      color:        "#fff",
      border:       "none",
      borderRadius: "5px",
      fontSize:     "11px",
      fontFamily:   "inherit",
      padding:      "3px 8px",
      cursor:       "pointer",
      flexShrink:   "0",
      transition:   "background 0.15s",
    });
    quitBtn.onmouseenter = () => quitBtn.style.background = "rgba(185,28,28,0.95)";
    quitBtn.onmouseleave = () => quitBtn.style.background = "rgba(220,38,38,0.85)";
    quitBtn.onclick = () => {
      quitBtn.textContent = "Stopping…";
      quitBtn.disabled = true;
      window.__agentQuitRequested = true;
      fetch(API_BASE + "/api/agent/quit", { method: "POST" }).catch(() => {});
    };
    el.appendChild(quitBtn);

    document.documentElement.appendChild(el);
  }

  // Update status text
  const txt = document.getElementById("agent-status-text");
  if (txt) txt.textContent = statusText;

  // Show/hide Skip button based on whether we're in a break/sleep state
  const skipBtn = document.getElementById("agent-skip-break-btn");
  if (skipBtn) {
    const lower = statusText.toLowerCase();
    const inBreak = lower.includes("break") || lower.includes("sleep")
                 || lower.includes("idle") || lower.includes("next session")
                 || lower.includes("catch-up idle") || lower.includes("min)");
    skipBtn.style.display = inBreak ? "block" : "none";
    if (inBreak && skipBtn.textContent !== "Skipping…") {
      skipBtn.textContent = "⏩ Skip";
      skipBtn.disabled = false;
    }
  }
}
""".replace("__PORT__", os.environ.get("DASHBOARD_API_PORT", "5001"))


async def set_status(text: str):
    if not text or _page is None:
        return
    if not _overlay_enabled():
        return
    try:
        if _page.is_closed():
            return
        await _page.evaluate(_OVERLAY_JS, text)
    except Exception:
        return


async def check_quit_button(page) -> bool:
    try:
        if page is None or page.is_closed():
            return False
        result = await page.evaluate("() => !!window.__agentQuitRequested")
        if result:
            set_quit_flag()
            return True
    except Exception:
        pass
    return quit_requested()


async def check_skip_break_button(page) -> bool:
    """Return True if the Skip Break button was clicked (or flag file exists)."""
    try:
        if page is None or page.is_closed():
            return skip_break_requested()
        result = await page.evaluate("() => !!window.__agentSkipBreak")
        if result:
            # Clear the in-page flag and set the file flag
            try:
                await page.evaluate("() => { window.__agentSkipBreak = false; }")
            except Exception:
                pass
            set_skip_break_flag()
            return True
    except Exception:
        pass
    return skip_break_requested()
