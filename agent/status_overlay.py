"""
status_overlay.py — Floating status bar overlay for the live browser.
Includes a Quit button that cleanly shuts down the agent process.
"""

import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
QUIT_FLAG_PATH = Path(__file__).parent.parent / "data" / "quit_flag"
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


def set_quit_flag():
    """Write the quit sentinel file so polling loops detect it."""
    QUIT_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUIT_FLAG_PATH.touch()


def clear_quit_flag():
    """Remove the quit sentinel at startup so stale flags don't block."""
    try:
        QUIT_FLAG_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def quit_requested() -> bool:
    """Return True if the Quit button has been clicked."""
    return QUIT_FLAG_PATH.exists()


_OVERLAY_JS = r"""
(statusText) => {
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
      gap:           "10px",
      maxWidth:      "80%",
      pointerEvents: "auto",
      userSelect:    "none",
    });

    // Status text span
    const txt = document.createElement("span");
    txt.id = "agent-status-text";
    Object.assign(txt.style, {
      overflow:     "hidden",
      textOverflow: "ellipsis",
      whiteSpace:   "nowrap",
      flex:         "1",
    });
    el.appendChild(txt);

    // Quit button
    const btn = document.createElement("button");
    btn.textContent = "✕ Quit";
    Object.assign(btn.style, {
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
    btn.onmouseenter = () => btn.style.background = "rgba(185,28,28,0.95)";
    btn.onmouseleave = () => btn.style.background = "rgba(220,38,38,0.85)";
    btn.onclick = () => {
      btn.textContent = "Stopping…";
      btn.disabled = true;
      // Signal Python via a flag exposed on window
      window.__agentQuitRequested = true;
      // Also write quit flag via fetch to the local agent API if available
      fetch("http://localhost:5000/api/quit", { method: "POST" }).catch(() => {});
    };
    el.appendChild(btn);

    document.documentElement.appendChild(el);
  }

  const txt = document.getElementById("agent-status-text");
  if (txt) txt.textContent = statusText;
}
"""


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
    """
    Poll the in-page window.__agentQuitRequested flag.
    Returns True if the user clicked Quit in the overlay.
    """
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

