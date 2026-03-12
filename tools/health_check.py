"""
tools/health_check.py — Pre-flight system check
Run this before starting the agent to verify everything is set up correctly.
Usage: python tools/health_check.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def check(label: str, passed: bool, detail: str = ""):
    icon = "✅" if passed else "❌"
    print(f"  {icon} {label}")
    if detail:
        print(f"     {detail}")
    return passed


def run_health_check():
    print("""
╔══════════════════════════════════════╗
║     TWITTER AGENT — HEALTH CHECK    ║
╚══════════════════════════════════════╝
""")

    all_passed = True

    # ── ENV FILE ─────────────────────────────────
    print("📋 ENVIRONMENT")
    from dotenv import load_dotenv
    load_dotenv()

    env_file = Path(".env")
    ok = check(".env file exists", env_file.exists(),
               "Run: cp .env.example .env" if not env_file.exists() else "")
    all_passed = all_passed and ok

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    key_set = bool(anthropic_key) or bool(openai_key)
    ok = check(
        "LLM API key set (Anthropic or OpenAI)",
        key_set,
        "Add ANTHROPIC_API_KEY or OPENAI_API_KEY to .env" if not key_set else ""
    )
    all_passed = all_passed and ok

    provider_pref = os.getenv("LLM_PROVIDER", "auto")
    try:
        from ai.llm_client import resolve_provider
        resolved_provider = resolve_provider(provider_pref)
        check("LLM provider", True, f"Using: {resolved_provider} (LLM_PROVIDER={provider_pref})")
    except Exception as e:
        check("LLM provider", False, str(e))
        all_passed = False
        resolved_provider = None

    username = os.getenv("TWITTER_USERNAME", "")
    ok = check("TWITTER_USERNAME set", bool(username) and username != "your_twitter_username",
               "Add your Twitter handle to .env" if not username else f"@{username}")
    all_passed = all_passed and ok

    # ── CONFIG ───────────────────────────────────
    print("\n📋 CONFIG")
    import yaml
    config_path = Path("config.yaml")
    ok = check("config.yaml exists", config_path.exists())
    all_passed = all_passed and ok

    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)

        targets = config.get("target_accounts", [])
        ok = check("Target accounts configured", len(targets) > 0,
                   f"{len(targets)} accounts in watchlist")
        all_passed = all_passed and ok

        product_url = config.get("voice", {}).get("product_url", "")
        ok = check("Product URL set", product_url != "https://yourproduct.com",
                   f"Current: {product_url}" if product_url != "https://yourproduct.com"
                   else "Update product_url in config.yaml")
        all_passed = all_passed and ok

    # ── VOICE PROFILE ────────────────────────────
    print("\n📋 VOICE PROFILE")
    voice_path = Path("ai/voice_profile.txt")
    ok = check("voice_profile.txt exists", voice_path.exists())
    all_passed = all_passed and ok

    if voice_path.exists():
        with open(voice_path) as f:
            content = f.read()
        ok = check("Voice profile has content", len(content) > 500,
                   f"{len(content)} characters")
        all_passed = all_passed and ok

    # ── PYTHON PACKAGES ──────────────────────────
    print("\n📋 PYTHON PACKAGES")
    core_packages = [
        ("playwright", "playwright"),
        ("playwright_stealth", "playwright-stealth"),
        ("flask", "flask"),
        ("yaml", "pyyaml"),
        ("schedule", "schedule"),
    ]

    for module, package in core_packages:
        try:
            __import__(module)
            check(f"{package}", True)
        except ImportError:
            check(f"{package}", False, f"Run: pip install {package}")
            all_passed = False

    provider_packages = []
    if anthropic_key or provider_pref == "anthropic":
        provider_packages.append(("anthropic", "anthropic"))
    if openai_key or provider_pref == "openai":
        provider_packages.append(("openai", "openai"))

    for module, package in provider_packages:
        try:
            __import__(module)
            check(f"{package}", True)
        except ImportError:
            check(f"{package}", False, f"Run: pip install {package}")
            all_passed = False

    # ── LLM API ──────────────────────────────────
    print("\n📋 LLM API")
    if key_set and resolved_provider:
        try:
            from ai.llm_client import chat_text, resolve_model

            model = resolve_model(kind="text", provider=resolved_provider)
            _ = chat_text(
                prompt="say ok",
                model=model,
                max_tokens=10,
                temperature=0,
                provider=resolved_provider,
            )
            ok = check("API connection works", True, f"Connected to {resolved_provider} ({model})")
        except Exception as e:
            ok = check("API connection works", False, str(e))
            all_passed = False
    else:
        check("API connection works", False, "No valid provider/key found — skipping test")
        all_passed = False

    # ── DATABASE ─────────────────────────────────
    print("\n📋 DATABASE")
    try:
        from agent.logger import init_db, get_today_stats
        init_db()
        stats = get_today_stats()
        check("SQLite database", True, f"Today: {stats}")
    except Exception as e:
        check("SQLite database", False, str(e))
        all_passed = False

    # ── SESSION ──────────────────────────────────
    print("\n📋 TWITTER SESSION")
    cookies_file = Path("data/twitter_cookies.json")
    ok = check("Twitter session saved", cookies_file.exists(),
               "Run: python main.py --test to log in" if not cookies_file.exists()
               else "Session cookies found — you're logged in")
    # Don't fail all_passed for this — user may not have logged in yet

    # ── SUMMARY ──────────────────────────────────
    print(f"""
{'═' * 42}
  {'✅ ALL CHECKS PASSED — Ready to run!' if all_passed else '❌ SOME CHECKS FAILED — Fix above issues first'}
{'═' * 42}
""")

    if all_passed:
        print("  Run the agent:    bash start.sh")
        print("  Or just agent:    python main.py")
        print("  Test voice only:  python tools/test_voice.py\n")
    else:
        print("  Fix the issues above then run this check again.\n")

    return all_passed


if __name__ == "__main__":
    run_health_check()
