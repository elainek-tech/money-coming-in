"""Telegram adapter: check the secret token, then turn an update into an InboundMessage."""

import hmac
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..models import InboundMessage

log = logging.getLogger("telegram")

# Shown on /start. Attendees are sending their own words to a demo screen.
CONSENT_TEXT = (
    "This is a demo. Your messages are analysed by AI and shown on a public screen. "
    "Please write as a made-up customer and don't share personal details."
)
ACK_TEXT = "Thanks! We got your message and someone will follow up."


def verify_secret(header_value: Optional[str], expected: Optional[str]) -> bool:
    """Telegram sends the secret you gave setWebhook in X-Telegram-Bot-Api-Secret-Token."""
    if not expected or not header_value:
        return False  # no secret configured means the webhook is closed
    return hmac.compare_digest(header_value, expected)


def normalize(update: dict) -> Optional[InboundMessage]:
    """Only private text messages from people. Everything else is ignored."""
    message = update.get("message")
    if not message:
        return None
    chat, sender, text = message.get("chat") or {}, message.get("from") or {}, message.get("text")
    if chat.get("type") != "private" or sender.get("is_bot") or not text:
        return None
    name = " ".join(part for part in (sender.get("first_name"), sender.get("last_name")) if part) or None
    return InboundMessage(
        channel="telegram",
        sender_id=str(sender.get("id", chat.get("id"))),
        text=text[:4000],
        display_name=name,
        message_id=f"tg-{update.get('update_id')}",  # update_id is unique, so retries are ignored
        timestamp=datetime.fromtimestamp(message.get("date", 0), tz=timezone.utc)
        if message.get("date")
        else datetime.now(timezone.utc),
    )


def send_text(bot_token: str, chat_id: str, text: str) -> None:
    """Fixed replies only (consent notice, acknowledgement). No AI chat."""
    try:
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
    except httpx.HTTPError:
        log.warning("telegram reply failed")  # never log the URL: it contains the bot token
