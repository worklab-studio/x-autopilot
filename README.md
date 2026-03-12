# Twitter Agent

AI-assisted Twitter automation agent with approval workflow, dashboard, and local browser/session control.

This project runs locally and supports both Claude and GPT providers.

## Quick Start

### 1. Install
```bash
bash setup.sh
```

### 2. Configure `.env`
```bash
cp .env.example .env
```

Fill in:

```env
LLM_PROVIDER=auto
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
TWITTER_USERNAME=your_handle
DASHBOARD_PASSWORD=your_password
SECRET_KEY=any_random_string
```

Notes:
- Add at least one key: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.
- `LLM_PROVIDER=auto` prefers Anthropic if both keys are present.
- Set `LLM_PROVIDER=openai` or `LLM_PROVIDER=anthropic` to force one.

### 3. Health check
```bash
source venv/bin/activate
python tools/health_check.py
```

### 4. Save Twitter session (one-time)
```bash
python main.py --test
```

### 5. Start dashboard + agent
```bash
bash start.sh
```

Dashboard:
- UI: `http://localhost:3000`
- API: `http://localhost:5001` (default)

## Model Overrides (Optional)

```env
ANTHROPIC_TEXT_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_VISION_MODEL=claude-3-5-sonnet-20241022
OPENAI_TEXT_MODEL=gpt-4o-mini
OPENAI_VISION_MODEL=gpt-4o-mini
```

## Core Commands

```bash
python tools/health_check.py
python tools/test_voice.py
python tools/dry_run.py
python main.py --test
python main.py
```

## Private Paid Distribution Docs

- Private release checklist: [`docs/PRIVATE_RELEASE.md`](docs/PRIVATE_RELEASE.md)
- Buyer setup guide: [`docs/BUYER_QUICKSTART.md`](docs/BUYER_QUICKSTART.md)
- License terms: [`LICENSE`](LICENSE)

## Security Notes

- Never commit `.env`.
- Never commit `data/twitter_cookies.json`.
- Keep repository private for paid distribution.

