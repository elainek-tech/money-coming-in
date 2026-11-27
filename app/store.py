"""Storage. One document per lead, with the conversation in a messages subcollection.

MemoryStore is for tests and local runs. FirestoreStore is for Cloud Run.
Both have the same small interface, so the pipeline never knows which one it has.
"""

import threading
from typing import Callable, Optional, Protocol


class Store(Protocol):
    def get_lead(self, key: str) -> Optional[dict]: ...
    def save_lead(self, key: str, data: dict) -> None: ...
    def add_message(self, key: str, message_id: str, data: dict) -> bool: ...  # False if already seen
    def recent_messages(self, key: str, limit: int) -> list[dict]: ...
    def subscribe(self, callback: Callable[[list[dict]], None]) -> Callable[[], None]: ...


class MemoryStore:
    def __init__(self):
        self._leads: dict[str, dict] = {}
        self._messages: dict[str, dict[str, dict]] = {}
        self._subscribers: list[Callable[[list[dict]], None]] = []
        self._lock = threading.Lock()

    def get_lead(self, key):
        lead = self._leads.get(key)
        return dict(lead) if lead else None

    def save_lead(self, key, data):
        with self._lock:
            self._leads[key] = {**self._leads.get(key, {}), **data}
            subscribers = list(self._subscribers)
        snapshot = self._snapshot()
        for callback in subscribers:
            callback(snapshot)

    def add_message(self, key, message_id, data):
        with self._lock:
            bucket = self._messages.setdefault(key, {})
            if message_id in bucket:
                return False
            bucket[message_id] = data
            return True

    def recent_messages(self, key, limit):
        items = sorted(self._messages.get(key, {}).values(), key=lambda m: m["timestamp"])
        return items[-limit:]

    def subscribe(self, callback):
        with self._lock:
            self._subscribers.append(callback)
        callback(self._snapshot())

        def unsubscribe():
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def _snapshot(self) -> list[dict]:
        return [{**lead, "key": key} for key, lead in self._leads.items()]


class FirestoreStore:
    def __init__(self, client=None):
        from google.cloud import firestore

        self._firestore = firestore
        self.db = client or firestore.Client()
        self.leads = self.db.collection("leads")

    def get_lead(self, key):
        doc = self.leads.document(key).get()
        return doc.to_dict() if doc.exists else None

    def save_lead(self, key, data):
        self.leads.document(key).set(data, merge=True)

    def add_message(self, key, message_id, data):
        from google.api_core.exceptions import AlreadyExists

        ref = self.leads.document(key).collection("messages").document(message_id.replace("/", "_"))
        try:
            ref.create(data)  # fails if it exists, which is how we ignore webhook retries
            return True
        except AlreadyExists:
            return False

    def recent_messages(self, key, limit):
        query = (
            self.leads.document(key)
            .collection("messages")
            .order_by("timestamp", direction=self._firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [doc.to_dict() for doc in reversed(list(query.stream()))]

    def subscribe(self, callback):
        # A real-time listener: Firestore calls us on the first load and on every change.
        def on_snapshot(docs, changes, read_time):
            callback([{**doc.to_dict(), "key": doc.id} for doc in docs])

        watch = self.leads.on_snapshot(on_snapshot)
        return watch.unsubscribe
