# 🚀 Twitter Agent — Quick Start Guide

**Total setup time: about 5 minutes.**
Follow the steps in order. You only do this once.

---

## Before You Start — What You Need

### 1. Python 3.9 or newer
Python is a free programming language the agent runs on.

→ Download from **https://python.org/downloads**
Click the big yellow button. Run the installer.

> ⚠️ **Windows users — critical step:**
> During the Python installer, check the box that says **"Add Python to PATH"**
> If you miss this, the agent won't find Python.

> **Mac users:** Python may already be installed. Setup will check for you.

### 2. An API Key (to power the AI)
You need one of these — either works:

**Option A — Anthropic (recommended)**
→ Sign up at **https://console.anthropic.com**
→ Go to API Keys → Create new key → Copy it

**Option B — OpenAI**
→ Sign up at **https://platform.openai.com/api-keys**
→ Create new secret key → Copy it

> 💡 Both have free credits to start. Day-to-day cost is roughly $0.10–$0.40/day at normal usage.

That's it. You do **not** need Node.js or any other software.

---

## Step 1 — Run Setup (one time only)

| Your computer | What to do |
|--------------|-----------|
| **Mac** | Double-click **`setup.command`** in the project folder |
| **Windows** | Double-click **`setup.bat`** in the project folder |

A black terminal window will open and automatically install everything. It takes **2–5 minutes** (it downloads a browser for automation).

When it says **SETUP COMPLETE ✅** you're ready.

---

### ⚠️ Mac — "cannot be opened" warning

macOS may block the file because it's from an unidentified developer.

**Fix:** Right-click `setup.command` → click **Open** → click **Open** in the popup.

You only need to do this once.

---

### ⚠️ Windows — SmartScreen warning

Windows may show *"Windows protected your PC"* when you double-click `setup.bat`.

**Fix:** Click **More info** → then click **Run anyway**.

---

## Step 2 — Launch the Agent

| Your computer | What to do |
|--------------|-----------|
| **Mac** | Double-click **`start.command`** |
| **Windows** | Double-click **`start.bat`** |

A browser window will open automatically to **http://localhost:5001**

This is your dashboard. You'll use it every day.

> You double-click **start** every time you want to run the agent.
> Setup only ever runs once.

---

## Step 3 — Add Your API Key

In the dashboard, click the **SETTINGS** tab at the top.

The very first section is **ACCOUNT & API KEYS**:

1. Type your **Twitter Username** (without the @ symbol)
2. Paste your **Anthropic API Key** (or OpenAI key in the fallback field)
3. Click **SAVE CREDENTIALS**

The green **SAVED** confirmation appears. Done.

---

## Step 4 — Log Into Twitter

The agent opens a Chrome browser window and navigates to Twitter.com.

- Log in with your normal username and password
- Complete any verification if Twitter asks (2FA, CAPTCHA, phone check)
- Once you're logged in, close that window — your session is saved permanently

You won't need to log in again unless Twitter expires your session.

---

## Step 5 — You're Running ✅

The dashboard at **http://localhost:5001** shows everything in real time.

---

## What Each Tab Does

| Tab | What it's for |
|-----|--------------|
| **Live Feed** | Watch every action as it happens — tweets, replies, follows, DMs |
| **Approval Queue** | Every AI-generated tweet appears here before posting. Review, edit, approve or skip. |
| **Voice Lab** | Tell the AI who you are — your niche, product, personality, topics |
| **Discovery** | Which accounts and hashtags to target. Add people you want to engage with. |
| **Promotions** | Add your products. The agent mentions them naturally at a frequency you control. |
| **Settings** | Every behaviour control — daily limits, timing, reply rates, safety settings |

---

## Every Day After Setup

1. Double-click `start.command` (Mac) or `start.bat` (Windows)
2. Your browser opens to the dashboard
3. Check the Approval Queue tab — approve or edit any queued tweets
4. That's it — the agent runs on its own

---

## Stopping the Agent

- Click **QUIT** in the top-right corner of the dashboard, OR
- Just close the terminal window

---

## Troubleshooting

| What you see | What to do |
|-------------|-----------|
| "Python not found" | Re-install Python from python.org and tick "Add to PATH" |
| Dashboard is blank / won't load | Re-run `setup.command` or `setup.bat` |
| "Port 5001 already in use" | The agent is already running — look for an open terminal window |
| Twitter asks you to log in again | A browser window will appear — log in normally, session saves automatically |
| The AI sounds nothing like me | Go to Voice Lab tab — fill in your niche, personality, and "never say" phrases |
| Tweets aren't posting | Check the Approval Queue — they may be waiting for your approval |

---

## Your Files Explained

| File / Folder | What it is |
|--------------|-----------|
| `setup.command` or `setup.bat` | First-time installer — run once |
| `start.command` or `start.bat` | Daily launcher — run every time |
| `.env` | Your API keys — keep this private, never share it |
| `config.yaml` | All settings — edited from the dashboard, you never need to touch this file directly |
| `data/` | Database, browser session, cookies — stays on your machine only |

---

## Still Stuck?

Check `README.md` in the project folder, or reach out for support.

The agent is designed to work for non-technical users — if setup is failing, it's a bug worth fixing.
