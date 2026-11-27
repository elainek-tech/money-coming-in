"""The whole pipeline in one function: store -> extract -> gate -> save -> publish."""

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from .events import Publisher
from .extract import MAX_MESSAGES, ExtractionError, Extractor
from .gate import diff_extractions, effective_status, next_status
from .models import InboundMessage, utcnow
from .store import Store

log = logging.getLogger("pipeline")


def process_message(
    msg: InboundMessage,
    *,
    store: Store,
    extractor: Extractor,
    publisher: Publisher,
    now: Optional[datetime] = None,
    dormant_after_days: int = 30,
) -> dict:
    now = now or utcnow()
    key = msg.lead_key

    # 1. Store the message first. A repeat of the same message_id (a webhook retry) stops here.
    message_id = msg.message_id or uuid4().hex
    is_new = store.add_message(
        key, message_id, {"text": msg.text, "timestamp": msg.timestamp, "channel": msg.channel}
    )
    if not is_new:
        return {"ok": True, "duplicate": True}

    # 2. Where was this lead before this message? (A long silence counts as dormant.)
    lead = store.get_lead(key)
    previous_status = effective_status(lead, now, dormant_after_days)

    # 3. Extract over the rolling conversation, old messages included.
    history = store.recent_messages(key, MAX_MESSAGES)
    try:
        extraction = extractor.extract(history)
    except ExtractionError as error:
        log.warning("extraction failed for %s: %s", key, error)
        return {"ok": False, "error": str(error)}

    # 4. Gate: rules turn facts into a status, and an event only when the status changes.
    status, event = next_status(previous_status, extraction)
    changes = diff_extractions(lead.get("extraction") if lead else None, extraction)
    version = (lead or {}).get("version", 0) + 1

    # 5. Save the lead (Firestore drives the live dashboard).
    record = {
        "channel": msg.channel,
        "sender_id": msg.sender_id,
        "status": status,
        "extraction": extraction.model_dump(),
        "version": version,
        "updated_at": now,
        "last_message_at": msg.timestamp,
    }
    if msg.display_name:
        record["display_name"] = msg.display_name
    if not lead:
        record["created_at"] = now
    if event:
        record["last_event"] = {"type": event, "changes": changes, "at": now}
    store.save_lead(key, record)

    # 6. Publish only on a transition. The dedupe key lets subscribers ignore repeats.
    if event:
        try:
            publisher.publish(
                event,
                {
                    "event": event,
                    "lead_key": key,
                    "channel": msg.channel,
                    "status": status,
                    "version": version,
                    "summary": extraction.summary,
                    "extraction": extraction.model_dump(),
                    "changes": changes,
                },
                dedupe_key=f"{key}:{version}:{event}",
            )
        except Exception:
            # The lead is already saved. In production, a separate Pub/Sub-driven writer
            # (or an outbox) removes this gap. See the "going further" note in the README.
            log.exception("publish failed for %s", key)

    return {"ok": True, "status": status, "event": event, "changes": changes, "version": version}
