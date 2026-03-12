# Buyer Quickstart

## Requirements

- macOS/Linux
- Python 3.9+
- Node.js + npm

## Setup

```bash
bash setup.sh
cp .env.example .env
```

## Configure `.env`

Set at least one LLM key:

```env
LLM_PROVIDER=auto
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
TWITTER_USERNAME=your_handle
DASHBOARD_PASSWORD=your_password
SECRET_KEY=any_random_string
```

## Validate

```bash
source venv/bin/activate
python tools/health_check.py
```

## Login Session (one-time)

```bash
python main.py --test
```

Log into Twitter in the opened browser, then return to terminal.

## Run

```bash
bash start.sh
```

Dashboard UI: `http://localhost:3000`

