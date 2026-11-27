"""The Cloud Run service: webhooks in, pipeline in the middle, live dashboard out."""

import asyncio
import hmac
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse

from .adapters import telegram, whatsapp
from .demo import seed_dormant_lead
from .events import LogPublisher, Publisher, PubSubPublisher
from .extract import Extractor, GeminiExtractor
from .models import InboundMessage
from .pipeline import process_message
from .store import FirestoreStore, MemoryStore, Store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

DASHBOARD = Path(__file__).parent / "static" / "dashboard.html"


@dataclass
class Settings:
    ingest_token: Optional[str] = None  # protects POST /messages (used by curl and the simulator)
    telegram_secret: Optional[str] = None  # the secret_token you pass to Telegram's setWebhook
    telegram_bot_token: Optional[str] = None  # optional: lets the bot send fixed replies
    whatsapp_verify_token: Optional[str] = None
    whatsapp_app_secret: Optional[str] = None
    gcp_project: Optional[str] = None  # set it to use Firestore
    pubsub_topic: Optional[str] = None  # a topic name, or a full projects/x/topics/y path
    dormant_after_days: int = 30
    demo_seed_sender: Optional[str] = None  # memory mode only: seed a dormant Telegram lead for this id

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            ingest_token=env("INGEST_TOKEN"),
            telegram_secret=env("TELEGRAM_WEBHOOK_SECRET"),
            telegram_bot_token=env("TELEGRAM_BOT_TOKEN"),
            whatsapp_verify_token=env("WHATSAPP_VERIFY_TOKEN"),
            whatsapp_app_secret=env("WHATSAPP_APP_SECRET"),
            gcp_project=env("GOOGLE_CLOUD_PROJECT"),
            pubsub_topic=env("PUBSUB_TOPIC"),
            dormant_after_days=int(env("DORMANT_AFTER_DAYS", "30")),
            demo_seed_sender=env("DEMO_SEED_SENDER"),
        )

    def topic_path(self) -> Optional[str]:
        if not self.pubsub_topic:
            return None
        if self.pubsub_topic.startswith("projects/"):
            return self.pubsub_topic
        return f"projects/{self.gcp_project}/topics/{self.pubsub_topic}" if self.gcp_project else None


def public_view(lead: dict) -> dict:
    """What the public dashboard may see: no sender id, no real name, no lead key.

    A WhatsApp sender id is a phone number and a Telegram display name is often a real name.
    Only simulated leads (display names starting 'Demo ') keep their label.
    """
    name = lead.get("display_name") or ""
    label = name if name.startswith("Demo ") else "customer …" + str(lead.get("sender_id", ""))[-3:]
    hidden = {"sender_id", "display_name", "key"}
    return {**{k: v for k, v in lead.items() if k not in hidden}, "label": label}


def create_app(
    settings: Optional[Settings] = None,
    store: Optional[Store] = None,
    extractor: Optional[Extractor] = None,
    publisher: Optional[Publisher] = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or (FirestoreStore() if settings.gcp_project else MemoryStore())
    extractor = extractor or GeminiExtractor()
    topic = settings.topic_path()
    publisher = publisher or (PubSubPublisher(topic) if topic else LogPublisher())

    if isinstance(store, MemoryStore) and settings.demo_seed_sender:
        seed_dormant_lead(store, "telegram", settings.demo_seed_sender)

    app = FastAPI(title="Money Coming In")

    def run(msg: InboundMessage) -> dict:
        return process_message(
            msg,
            store=store,
            extractor=extractor,
            publisher=publisher,
            dormant_after_days=settings.dormant_after_days,
        )

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "store": type(store).__name__, "publisher": type(publisher).__name__}

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return DASHBOARD.read_text(encoding="utf-8")

    @app.get("/stream")
    async def stream(request: Request):
        """Server-sent events: the store's real-time listener pushes every change to the browser."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)

        def put(leads):  # runs on the event loop
            if queue.full():
                queue.get_nowait()  # drop the oldest, keep the newest snapshot
            queue.put_nowait(leads)

        unsubscribe = store.subscribe(lambda leads: loop.call_soon_threadsafe(put, leads))

        async def events():
            try:
                while not await request.is_disconnected():
                    try:
                        leads = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {json.dumps([public_view(l) for l in leads], default=str)}\n\n"
            finally:
                unsubscribe()

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/messages")
    def ingest(msg: InboundMessage, x_ingest_token: Optional[str] = Header(default=None)):
        """Generic entry point for curl, the simulator and any other channel."""
        if not settings.ingest_token:
            raise HTTPException(503, "INGEST_TOKEN is not set, so this endpoint is closed.")
        if not x_ingest_token or not hmac.compare_digest(x_ingest_token, settings.ingest_token):
            raise HTTPException(403, "Bad token.")
        result = run(msg)
        if not result.get("ok"):
            raise HTTPException(502, result.get("error", "Extraction failed."))
        return result

    @app.post("/webhooks/telegram")
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
    ):
        if not telegram.verify_secret(x_telegram_bot_api_secret_token, settings.telegram_secret):
            raise HTTPException(403, "Bad secret token.")
        update = await request.json()
        token = settings.telegram_bot_token

        text = ((update.get("message") or {}).get("text") or "").strip()
        if text.startswith("/start"):
            if token:
                chat_id = str(update["message"]["chat"]["id"])
                await run_in_threadpool(telegram.send_text, token, chat_id, telegram.CONSENT_TEXT)
            return {"ok": True}

        msg = telegram.normalize(update)
        if msg is None:
            return {"ok": True, "ignored": True}
        # Process inside the request: Cloud Run may pause the CPU once the response is sent.
        # A retry from Telegram is harmless because the update id makes the message idempotent.
        result = await run_in_threadpool(run, msg)
        if token and result.get("ok") and not result.get("duplicate"):
            await run_in_threadpool(telegram.send_text, token, msg.sender_id, telegram.ACK_TEXT)
        return {"ok": True}  # always 200, so Telegram does not hammer us with retries

    @app.get("/webhooks/whatsapp")
    def whatsapp_verify(request: Request):
        challenge = whatsapp.verify_challenge(dict(request.query_params), settings.whatsapp_verify_token)
        if challenge is None:
            raise HTTPException(403, "Verification failed.")
        return PlainTextResponse(challenge)

    @app.post("/webhooks/whatsapp")
    async def whatsapp_webhook(
        request: Request,
        x_hub_signature_256: Optional[str] = Header(default=None),
    ):
        body = await request.body()
        if not whatsapp.verify_signature(body, x_hub_signature_256, settings.whatsapp_app_secret):
            raise HTTPException(403, "Bad signature.")
        messages = whatsapp.normalize(json.loads(body))
        for msg in messages:
            await run_in_threadpool(run, msg)
        return {"ok": True, "processed": len(messages)}

    return app


app = create_app()
