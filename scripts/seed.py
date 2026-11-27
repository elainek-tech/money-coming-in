"""Seed the dormant lead for the recycled-lead demo (Firestore).

  uv run python -m scripts.seed --list                   recent leads: pick the one that is you
  uv run python -m scripts.seed --key telegram:123456    turn that lead into the dormant 'budget too low' lead

Workflow: message your bot once, run --list privately to find your key, then --key.
Needs GOOGLE_CLOUD_PROJECT and credentials (gcloud auth application-default login).
"""

import argparse
import os
import sys

from app.demo import seed_dormant_lead
from app.store import FirestoreStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list recent leads (keys can contain phone numbers: keep private)")
    parser.add_argument("--key", help="lead key as channel:sender_id, for example telegram:123456")
    args = parser.parse_args()

    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        print("Set GOOGLE_CLOUD_PROJECT first.")
        return 1
    store = FirestoreStore()

    if args.list:
        for doc in store.leads.order_by("updated_at", direction="DESCENDING").limit(15).stream():
            lead = doc.to_dict()
            print(f"{doc.id:<28} {lead.get('display_name') or '-':<20} {lead.get('status')}")
        return 0

    if not args.key or ":" not in args.key:
        parser.error("give --key channel:sender_id, or use --list")
    channel, sender_id = args.key.split(":", 1)
    seed_dormant_lead(store, channel, sender_id)
    print(f"Seeded {args.key} as a dormant lead. Now message from that account.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
