"""WhatsApp Cloud API adapter. Parses incoming-message webhooks into InboundMessages.

Verify these details against Meta's current webhook reference before you rely on them:
the GET verification parameters and the X-Hub-Signature-256 header.
"""

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional

from ..models import InboundMessage


def verify_challenge(params: dict, expected_token: Optional[str]) -> Optional[str]:
    """Meta calls GET with hub.mode, hub.verify_token and hub.challenge when you save the webhook."""
    if (
        expected_token
        and params.get("hub.mode") == "subscribe"
        and hmac.compare_digest(params.get("hub.verify_token", ""), expected_token)
    ):
        return params.get("hub.challenge")
    return None


def verify_signature(body: bytes, header_value: Optional[str], app_secret: Optional[str]) -> bool:
    """HMAC-SHA256 of the raw body with your app secret, sent as 'sha256=<hex>'."""
    if not app_secret or not header_value or not header_value.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header_value.removeprefix("sha256="), expected)


def normalize(payload: dict) -> list[InboundMessage]:
    """One webhook can carry several messages. Delivery receipts (statuses) are ignored."""
    found: list[InboundMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
            for message in value.get("messages", []):
                text = (message.get("text") or {}).get("body")
                if message.get("type") != "text" or not text:
                    continue
                sender = message.get("from", "")
                found.append(
                    InboundMessage(
                        channel="whatsapp",
                        sender_id=sender,
                        text=text[:4000],
                        display_name=names.get(sender),
                        message_id=f"wa-{message.get('id')}",
                        timestamp=datetime.fromtimestamp(int(message.get("timestamp", 0)), tz=timezone.utc)
                        if message.get("timestamp")
                        else datetime.now(timezone.utc),
                    )
                )
    return found
