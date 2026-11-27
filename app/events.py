"""Publishing lead events. Pub/Sub can deliver a message more than once, so every event
carries a dedupe_key (lead + version + event) that subscribers can use to ignore repeats."""

import json
import logging
from typing import Protocol

log = logging.getLogger("events")


class Publisher(Protocol):
    def publish(self, event_type: str, payload: dict, dedupe_key: str) -> None: ...


class LogPublisher:
    """Used when no topic is configured (local runs and tests). Keeps events in memory."""

    def __init__(self):
        self.events: list[dict] = []

    def publish(self, event_type, payload, dedupe_key):
        self.events.append({"type": event_type, "payload": payload, "dedupe_key": dedupe_key})
        log.info("event %s %s", event_type, dedupe_key)


class PubSubPublisher:
    def __init__(self, topic_path: str, client=None):
        from google.cloud import pubsub_v1

        self.topic_path = topic_path
        self.client = client or pubsub_v1.PublisherClient()

    def publish(self, event_type, payload, dedupe_key):
        data = json.dumps(payload, default=str).encode("utf-8")
        future = self.client.publish(self.topic_path, data, event_type=event_type, dedupe_key=dedupe_key)
        future.result(timeout=10)  # wait, so a failure is visible in the logs rather than lost
