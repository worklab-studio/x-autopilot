"""
tools/test_voice.py — Interactive voice testing tool
Test tweet/reply/DM generation WITHOUT running the browser or posting anything.
Use this to tune your voice profile until everything sounds right.

Usage: python tools/test_voice.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


def divider(char="─", width=50):
    print(char * width)


def print_tweet(content: str, label: str = "GENERATED"):
    divider()
    print(f"  [{label}]")
    divider()
    print(f"\n  {content}\n")
    divider()
    print(f"  {len(content)}/280 characters")


def ask(prompt: str, options: list = None) -> str:
    if options:
        print(f"\n{prompt}")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        while True:
            choice = input("\n  → ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                return options[int(choice) - 1]
            print("  Invalid choice, try again")
    else:
        return input(f"\n{prompt}\n  → ").strip()


def main():
    from ai.tweet_writer import (
        generate_tweet, generate_reply,
        generate_dm_opener, generate_thread
    )

    print("""
╔══════════════════════════════════════╗
║     VOICE LAB — TWEET TESTER        ║
║     Nothing gets posted here        ║
╚══════════════════════════════════════╝

Test how the AI writes as you before letting it run.
Every output is just a preview — zero risk.
""")

    while True:
        mode = ask("What do you want to test?", [
            "Generate a tweet",
            "Generate a reply (by follower tier)",
            "Generate a DM opener",
            "Generate a full thread",
            "Batch test — generate 5 tweets at once",
            "Exit",
        ])

        if mode == "Generate a tweet":
            tweet_type = ask("Tweet type:", [
                "hot_take",
                "build_update",
                "personal",
                "resource",
                "auto (agent decides)",
            ])
            tweet_type = tweet_type.split(" ")[0]

            topic = ask("Topic (press Enter to let AI decide):") or None

            print("\n⏳ Generating...")
            content = generate_tweet(tweet_type=tweet_type, topic=topic)
            print_tweet(content)

            feedback = ask("How does it sound?", [
                "Perfect — add to queue",
                "Regenerate",
                "Back to menu",
            ])

            if feedback == "Perfect — add to queue":
                from agent.logger import add_to_tweet_queue
                tweet_id = add_to_tweet_queue(content)
                print(f"\n  ✅ Added to approval queue (ID: {tweet_id})")
                print("  Open the dashboard to approve it → http://localhost:3000\n")

            elif feedback == "Regenerate":
                print("\n⏳ Regenerating...")
                content = generate_tweet(tweet_type=tweet_type, topic=topic)
                print_tweet(content)

        elif mode == "Generate a reply (by follower tier)":
            tier = ask("Account tier:", ["small (0–1k)", "peer (1k–10k)", "big (10k+)"])
            tier_key = tier.split(" ")[0]

            followers_map = {"small": 500, "peer": 3000, "big": 50000}
            followers = followers_map[tier_key]

            tweet_text = ask("Paste the tweet you want to reply to:")
            author = ask("Their Twitter username (without @):") or "example_user"

            print("\n⏳ Generating reply...")
            reply = generate_reply(
                tweet_text=tweet_text,
                author=author,
                author_followers=followers,
                tier=tier_key,
                extra_context=None
            )
            print_tweet(reply, label=f"REPLY [{tier_key.upper()} TIER]")

        elif mode == "Generate a DM opener":
            username = ask("Their username (without @):") or "example_user"
            their_tweet = ask("Their tweet you replied to:")
            your_comment = ask("The comment you left on their tweet:")

            print("\n⏳ Generating DM opener...")
            dm = generate_dm_opener(
                username=username,
                their_tweet=their_tweet,
                your_comment=your_comment
            )
            print_tweet(dm, label="DM OPENER")

        elif mode == "Generate a full thread":
            topic = ask("Thread topic (e.g. 'why most SaaS landing pages fail'):") or "indie hacking in 2026"
            num = ask("Number of tweets:", ["3", "4", "5", "6"])

            print(f"\n⏳ Generating {num}-tweet thread...")
            tweets = generate_thread(topic=topic, num_tweets=int(num))

            print("\n" + "═" * 50)
            print(f"  THREAD: {topic}")
            print("═" * 50)
            for i, tweet in enumerate(tweets, 1):
                print(f"\n  [{i}/{len(tweets)}] {tweet}")
                print(f"  {len(tweet)}/280 chars")
                divider("·")

            add = ask("Add to approval queue?", ["Yes", "No"])
            if add == "Yes":
                from agent.logger import add_to_tweet_queue
                for i, tweet in enumerate(tweets):
                    add_to_tweet_queue(tweet, scheduled_for=f"Thread {i+1}/{len(tweets)}")
                print(f"\n  ✅ {len(tweets)} tweets added to queue")

        elif mode == "Batch test — generate 5 tweets at once":
            print("\n⏳ Generating 5 tweets in different styles...")
            types = ["hot_take", "build_update", "personal", "resource", "auto"]
            results = []

            for tweet_type in types:
                content = generate_tweet(tweet_type=tweet_type)
                results.append((tweet_type, content))

            print("\n" + "═" * 50)
            print("  BATCH RESULTS — 5 TWEET STYLES")
            print("═" * 50)

            for tweet_type, content in results:
                print(f"\n  [{tweet_type.upper()}]")
                print(f"  {content}")
                print(f"  {len(content)}/280")
                divider("·")

            print("\n  Review these and update ai/voice_profile.txt if any style feels off.")

        elif mode == "Exit":
            print("\n  Voice Lab closed. Run the agent: bash start.sh\n")
            break

        print()


if __name__ == "__main__":
    main()
