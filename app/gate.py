"""The gate: plain rules that turn extracted facts into a lead status.

The model only extracts facts. Code decides what they mean. That keeps the
decision testable, tunable and explainable.
"""

from datetime import datetime, timedelta
from typing import Optional

from .schema import Extraction

QUALIFY_INTENTS = {"buy", "enquire"}
MIN_URGENCY = 3
MIN_CONFIDENCE = 0.6

# Statuses: active -> qualified, or dormant -> recycled. "new" only exists before the first extraction.
EVENT_QUALIFIED = "lead.qualified"
EVENT_RECYCLED = "lead.recycled"


def passes_gate(e: Extraction) -> bool:
    """Qualified = wants to buy soon, said what they can spend, and can decide (or might)."""
    return (
        e.intent in QUALIFY_INTENTS
        and e.urgency_score >= MIN_URGENCY
        and e.confidence >= MIN_CONFIDENCE
        and e.budget_stated
        and e.decision_maker != "no"
    )


def effective_status(lead: Optional[dict], now: datetime, dormant_after_days: int) -> Optional[str]:
    """Status as of now. An active lead that has been silent too long counts as dormant."""
    if not lead:
        return None
    status = lead.get("status")
    last = lead.get("last_message_at")
    if status == "active" and last is not None:
        if now - last > timedelta(days=dormant_after_days):
            return "dormant"
    return status


def next_status(previous: Optional[str], e: Extraction) -> tuple[str, Optional[str]]:
    """Return (new_status, event_to_publish_or_None). Events fire only on a transition."""
    ok = passes_gate(e)
    if previous in (None, "active"):
        return ("qualified", EVENT_QUALIFIED) if ok else ("active", None)
    if previous == "dormant":
        return ("recycled", EVENT_RECYCLED) if ok else ("dormant", None)
    # qualified and recycled are sticky: no downgrade, no repeat event.
    return previous, None


TRACKED_FIELDS = ("intent", "budget_amount", "budget_currency", "decision_maker", "urgency_score", "objection")


def diff_extractions(old: Optional[dict], new: Extraction) -> dict[str, dict]:
    """What changed since the last extraction. Shown on the dashboard and in the event."""
    if not old:
        return {}
    new_values = new.model_dump()
    return {
        field: {"from": old.get(field), "to": new_values[field]}
        for field in TRACKED_FIELDS
        if old.get(field) != new_values[field]
    }
