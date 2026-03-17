# Twitter Growth Agent

> AI-powered Twitter automation — runs locally on your Mac or Windows PC.
> One-time setup. No monthly fees. Your API key. Your data.

---

## 👋 First time here? Start with the Quick Start Guide

→ **[docs/BUYER_QUICKSTART.md](docs/BUYER_QUICKSTART.md)**

That guide walks you through the full setup in plain language with no assumed knowledge.

---

## The Short Version

### Requirements
- **Python 3.9+** — https://python.org/downloads
  - Windows: check ✅ "Add Python to PATH" during install
- **An API key** — Anthropic (https://console.anthropic.com) or OpenAI (https://platform.openai.com/api-keys)
- Node.js is **not required** (the dashboard comes pre-built)

### First-time Setup (once only)

| Mac | Windows |
|-----|---------|
| Double-click **`setup.command`** | Double-click **`setup.bat`** |

Takes 2–5 minutes. Installs Python packages + downloads the automation browser.

> **Mac:** If you see *"cannot be opened because it is from an unidentified developer"*
> → Right-click the file → **Open** → **Open**

> **Windows:** If SmartScreen warns you → click **More info** → **Run anyway**

### Launch (every time)

| Mac | Windows |
|-----|---------|
| Double-click **`start.command`** | Double-click **`start.bat`** |

Your browser opens automatically to **http://localhost:5001**

### First Launch — Add Your Keys

1. Click the **SETTINGS** tab in the dashboard
2. Fill in **ACCOUNT & API KEYS** at the top:
   - Your Twitter username (without @)
   - Your Anthropic API key (or OpenAI as fallback)
3. Click **SAVE CREDENTIALS**
4. Log into Twitter when the browser window opens

That's it. The agent starts running.

---

## Dashboard Tabs

| Tab | What it does |
|-----|-------------|
| **Live Feed** | Real-time log of every action |
| **Approval Queue** | AI tweets waiting for your review before posting |
| **Voice Lab** | Edit the AI's writing style and personality |
| **Discovery** | Hashtags + auto-discovered target accounts (no manual list needed) |
| **Promotions** | Subtle product mentions woven into replies when topics match |
| **Settings** | All behaviour controls — limits, timing, safety |

---

## Stopping the Agent

- Click **QUIT** in the dashboard top bar, or
- Close the terminal window that opened when you double-clicked start

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Python not found" | Re-install Python and tick "Add to PATH" |
| Dashboard is blank | Re-run `setup.command` / `setup.bat` |
| Port 5001 in use | The agent is already running — check your taskbar |
| Browser stuck on X logo | Normal on first launch — agent clears it automatically and navigates to login |
| Twitter login needed again | A browser window will open to the login page — log in normally |

---

## Files You Should Know About

| File | Purpose |
|------|---------|
| `setup.command` / `setup.bat` | First-time setup (run once) |
| `start.command` / `start.bat` | Launch the agent (run every time) |
| `.env` | Your API keys (auto-created, never share this file) |
| `config.yaml` | All agent settings (editable from the dashboard) |
| `data/` | Database, session, cookies — stays on your machine |

---

*Questions? See the full guide in [docs/BUYER_QUICKSTART.md](docs/BUYER_QUICKSTART.md)*
