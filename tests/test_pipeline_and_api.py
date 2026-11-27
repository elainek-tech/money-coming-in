import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.demo import seed_dormant_lead
from app.demo_data import CONVERSATION, RECYCLE_MESSAGE
from app.main import Settings, create_app
from app.models import InboundMessage
from app.pipeline import process_message


def send(text, store, extractor, publisher, sender="u1", message_id=None, channel="telegram"):
    return process_message(
        InboundMessage(channel=channel, sender_id=sender, text=text, message_id=message_id),
        store=store, extractor=extractor, publisher=publisher,
    )


def test_a_conversation_warms_up_and_publishes_exactly_one_event(store, extractor, publisher):
    results = [send(text, store, extractor, publisher) for text in CONVERSATION]
    assert [r["status"] for r in results] == ["active", "active", "qualified"]
    assert [r["event"] for r in results] == [None, None, "lead.qualified"]
    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert event["dedupe_key"] == "telegram:u1:3:lead.qualified"
    assert event["payload"]["extraction"]["budget_amount"] == 60000

    # A fourth message from a qualified lead does not publish again.
    again = send("Thanks!", store, extractor, publisher)
    assert again["status"] == "qualified" and again["event"] is None
    assert len(publisher.events) == 1


def test_retries_with_the_same_message_id_are_ignored(store, extractor, publisher):
    first = send("Hi, do you do kitchen renovations?", store, extractor, publisher, message_id="tg-1")
    retry = send("Hi, do you do kitchen renovations?", store, extractor, publisher, message_id="tg-1")
    assert first["ok"] and retry == {"ok": True, "duplicate": True}
    assert extractor.calls == 1
    assert store.get_lead("telegram:u1")["version"] == 1


def test_a_dormant_lead_is_recycled_when_the_sender_returns(store, extractor, publisher):
    key = seed_dormant_lead(store, "telegram", "777")
    assert store.get_lead(key)["status"] == "dormant"

    result = send(RECYCLE_MESSAGE, store, extractor, publisher, sender="777")
    assert result["status"] == "recycled" and result["event"] == "lead.recycled"
    assert result["changes"]["budget_amount"] == {"from": 15000.0, "to": 45000}
    assert result["changes"]["objection"] == {"from": "budget too low", "to": None}
    assert [e["type"] for e in publisher.events] == ["lead.recycled"]
    lead = store.get_lead(key)
    assert lead["last_event"]["type"] == "lead.recycled" and lead["version"] == 2


def test_a_dormant_lead_that_returns_without_a_reason_stays_dormant(store, extractor, publisher):
    key = seed_dormant_lead(store, "telegram", "888")
    result = send("hello again", store, extractor, publisher, sender="888")
    assert result["status"] == "dormant" and result["event"] is None
    assert publisher.events == []
    assert store.get_lead(key)["status"] == "dormant"


def test_spam_is_never_qualified(store, extractor, publisher):
    result = send("CONGRATULATIONS! You won a free cruise, click here now.", store, extractor, publisher)
    assert result["status"] == "active" and publisher.events == []


def test_extraction_failure_changes_nothing_and_publishes_nothing(store, extractor, publisher):
    send("Hi, do you do kitchen renovations?", store, extractor, publisher)
    before = store.get_lead("telegram:u1")
    extractor.fail = True
    result = send("Budget is around RM60k.", store, extractor, publisher)
    assert result["ok"] is False
    assert store.get_lead("telegram:u1") == before
    assert publisher.events == []


def test_a_publish_failure_does_not_lose_the_saved_lead(store, extractor):
    class Broken:
        def publish(self, *args, **kwargs):
            raise RuntimeError("pubsub down")

    result = process_message(
        InboundMessage(channel="telegram", sender_id="u9", text="Budget is around RM60k."),
        store=store, extractor=extractor, publisher=Broken(),
    )
    assert result["ok"] and result["status"] == "qualified"
    assert store.get_lead("telegram:u9")["status"] == "qualified"


# ---- HTTP layer ----

def make_client(extractor, publisher, store=None, **settings):
    from app.store import MemoryStore

    store = store or MemoryStore()
    app = create_app(Settings(**settings), store=store, extractor=extractor, publisher=publisher)
    return TestClient(app), store


def test_messages_endpoint_requires_the_token(extractor, publisher):
    body = {"channel": "web", "sender_id": "a", "text": "Budget is around RM60k."}
    closed, _ = make_client(extractor, publisher)  # no INGEST_TOKEN configured
    assert closed.post("/messages", json=body).status_code == 503

    client, store = make_client(extractor, publisher, ingest_token="dev")
    assert client.post("/messages", json=body).status_code == 403
    assert client.post("/messages", json=body, headers={"X-Ingest-Token": "nope"}).status_code == 403
    ok = client.post("/messages", json=body, headers={"X-Ingest-Token": "dev"})
    assert ok.status_code == 200 and ok.json()["status"] == "qualified"
    assert store.get_lead("web:a")["status"] == "qualified"


def test_messages_endpoint_reports_a_model_failure_as_502(extractor, publisher):
    extractor.fail = True
    client, _ = make_client(extractor, publisher, ingest_token="dev")
    r = client.post("/messages", json={"channel": "web", "sender_id": "a", "text": "hi"},
                    headers={"X-Ingest-Token": "dev"})
    assert r.status_code == 502


def test_telegram_webhook_checks_the_secret_and_processes_updates(extractor, publisher):
    client, store = make_client(extractor, publisher, telegram_secret="s3cret")
    update = {"update_id": 7, "message": {"message_id": 1, "from": {"id": 5, "is_bot": False, "first_name": "Li"},
              "chat": {"id": 5, "type": "private"}, "date": 1_700_000_000, "text": "Budget is around RM60k."}}
    assert client.post("/webhooks/telegram", json=update).status_code == 403
    assert client.post("/webhooks/telegram", json=update,
                       headers={"X-Telegram-Bot-Api-Secret-Token": "bad"}).status_code == 403
    good = {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}
    assert client.post("/webhooks/telegram", json=update, headers=good).json() == {"ok": True}
    assert store.get_lead("telegram:5")["status"] == "qualified"
    # Telegram retries are harmless.
    client.post("/webhooks/telegram", json=update, headers=good)
    assert extractor.calls == 1
    # Non-message updates are acknowledged and ignored.
    assert client.post("/webhooks/telegram", json={"update_id": 8}, headers=good).json()["ignored"] is True


def test_whatsapp_webhook_verifies_and_processes(extractor, publisher):
    client, store = make_client(extractor, publisher, whatsapp_verify_token="tok", whatsapp_app_secret="appsecret")
    params = {"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "999"}
    assert client.get("/webhooks/whatsapp", params=params).text == "999"
    assert client.get("/webhooks/whatsapp", params={**params, "hub.verify_token": "x"}).status_code == 403

    payload = {"entry": [{"changes": [{"field": "messages", "value": {"messages": [
        {"from": "6011", "id": "wamid.1", "timestamp": "1700000000", "type": "text",
         "text": {"body": "Budget is around RM60k."}}]}}]}]}
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
    assert client.post("/webhooks/whatsapp", content=body).status_code == 403
    ok = client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": signature})
    assert ok.json() == {"ok": True, "processed": 1}
    assert store.get_lead("whatsapp:6011")["status"] == "qualified"


def test_dashboard_and_health(extractor, publisher):
    client, _ = make_client(extractor, publisher)
    assert client.get("/healthz").json()["ok"] is True
    page = client.get("/")
    assert page.status_code == 200 and "EventSource('/stream')" in page.text
    # Attendee text must never be injected as HTML.
    for unsafe in (".innerHTML", "insertAdjacentHTML", "document.write", "outerHTML"):
        assert unsafe not in page.text


def test_stream_pushes_the_current_leads(extractor, publisher):
    from app.store import MemoryStore

    store = MemoryStore()
    seed_dormant_lead(store, "telegram", "777")
    client, _ = make_client(extractor, publisher, store=store)
    with client.stream("GET", "/stream") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        first = next(line for line in response.iter_lines() if line.startswith("data: "))
    leads = json.loads(first.removeprefix("data: "))
    assert leads[0]["label"] == "Demo customer" and leads[0]["status"] == "dormant"
    assert "key" not in leads[0] and "sender_id" not in leads[0]


def test_public_view_hides_identifiers():
    from app.main import public_view
    lead = {"key": "telegram:5551234", "sender_id": "5551234", "display_name": "Real Name",
            "channel": "telegram", "status": "active"}
    view = public_view(lead)
    assert "5551234" not in str(view).replace("…234", "")
    assert "Real Name" not in str(view)
    assert view["label"].endswith("234")
    assert public_view({"sender_id": "x1", "display_name": "Demo x1"})["label"] == "Demo x1"
