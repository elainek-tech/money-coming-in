"""The one internal message shape. Every channel adapter produces this."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InboundMessage(BaseModel):
    channel: str = Field(min_length=1, max_length=32)  # "telegram", "whatsapp", "web", ...
    sender_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    display_name: Optional[str] = Field(default=None, max_length=120)
    message_id: Optional[str] = Field(default=None, max_length=256)  # used to ignore retries
    timestamp: datetime = Field(default_factory=utcnow)

    @property
    def lead_key(self) -> str:
        """One lead per person per channel. Old and new messages share this key."""
        return f"{self.channel}:{self.sender_id}".replace("/", "_")
