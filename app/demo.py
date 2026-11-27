"""Seed one dormant lead, so the live 'recycled' moment has something to wake up."""

from datetime import timedelta

from .demo_data import DORMANT_OLD_MESSAGES
from .models import utcnow
from .store import Store


def seed_dormant_lead(store: Store, channel: str, sender_id: str, display_name: str = "Demo customer") -> str:
    key = f"{channel}:{sender_id}".replace("/", "_")
    long_ago = utcnow() - timedelta(days=200)
    for index, text in enumerate(DORMANT_OLD_MESSAGES):
        store.add_message(
            key,
            f"seed-{index}",
            {"text": text, "timestamp": long_ago + timedelta(minutes=index), "channel": channel},
        )
    store.save_lead(
        key,
        {
            "channel": channel,
            "sender_id": sender_id,
            "display_name": display_name,
            "status": "dormant",
            "version": 1,
            "created_at": long_ago,
            "updated_at": long_ago,
            "last_message_at": long_ago + timedelta(minutes=1),
            "extraction": {
                "intent": "enquire",
                "budget_amount": 15000.0,
                "budget_currency": "MYR",
                "decision_maker": "yes",
                "urgency_score": 2,
                "objection": "budget too low",
                "summary": "Wants a full terrace-house renovation but only has RM15k, so they paused.",
                "evidence": ["RM15k is all we have"],
                "confidence": 0.9,
            },
        },
    )
    return key
