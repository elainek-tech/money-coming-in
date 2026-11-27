"""Send the fictional sample messages to a running service.

  uv run python -m scripts.simulate singles                 six single messages, six senders
  uv run python -m scripts.simulate conversation            one chat, three messages, watch it warm up
  uv run python -m scripts.simulate recycle --sender 12345  the message that wakes a seeded dormant lead

Needs INGEST_TOKEN in the environment. Use --url for a deployed service.
"""

import argparse
import os
import sys
import time

import httpx

from app.demo_data import CONVERSATION, RECYCLE_MESSAGE, SINGLE_MESSAGES


def post(client: httpx.Client, url: str, token: str, sender: str, text: str, channel: str) -> None:
    response = client.post(
        f"{url}/messages",
        headers={"X-Ingest-Token": token},
        json={"channel": channel, "sender_id": sender, "text": text, "display_name": f"Demo {sender}"},
        timeout=60,
    )
    if response.status_code != 200:
        print(f"  ! {response.status_code}: {response.text[:200]}")
        return
    result = response.json()
    print(f"  {result.get('status'):<10} event={result.get('event')}  | {text[:60]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=["singles", "conversation", "recycle"])
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--sender", default="demo-conversation", help="sender id (recycle: the seeded lead's id)")
    parser.add_argument("--channel", default="sim", help="use 'telegram' with --sender <id> to hit a seeded Telegram lead")
    parser.add_argument("--pause", type=float, default=3.0, help="seconds between conversation messages")
    args = parser.parse_args()

    token = os.environ.get("INGEST_TOKEN")
    if not token:
        print("Set INGEST_TOKEN first (the same value the service uses).")
        return 1

    with httpx.Client() as client:
        if args.what == "singles":
            for index, text in enumerate(SINGLE_MESSAGES, start=1):
                post(client, args.url, token, f"demo-single-{index}", text, args.channel)
        elif args.what == "conversation":
            for text in CONVERSATION:
                post(client, args.url, token, args.sender, text, args.channel)
                time.sleep(args.pause)
        else:
            post(client, args.url, token, args.sender, RECYCLE_MESSAGE, args.channel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
