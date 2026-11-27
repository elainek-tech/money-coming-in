import hashlib
import hmac
import json

from app.adapters import telegram, whatsapp

PRIVATE_UPDATE = {
    "update_id": 1001,
    "message": {
        "message_id": 5,
        "from": {"id": 42, "is_bot": False, "first_name": "Aina", "last_name": "Tan"},
        "chat": {"id": 42, "type": "private"},
        "date": 1_700_000_000,
        "text": "Hi, do you do kitchen renovations?",
    },
}


def test_telegram_secret_must_match_and_be_configured():
    assert telegram.verify_secret("s3cret", "s3cret")
    assert not telegram.verify_secret("wrong", "s3cret")
    assert not telegram.verify_secret(None, "s3cret")
    assert not telegram.verify_secret("anything", None)  # no secret configured: closed
    assert not telegram.verify_secret("anything", "")


def test_telegram_normalizes_a_private_text_message():
    msg = telegram.normalize(PRIVATE_UPDATE)
    assert msg.channel == "telegram" and msg.sender_id == "42"
    assert msg.display_name == "Aina Tan"
    assert msg.message_id == "tg-1001"
    assert msg.text == "Hi, do you do kitchen renovations?"
    assert msg.lead_key == "telegram:42"


def test_telegram_ignores_groups_bots_and_non_text():
    group = {**PRIVATE_UPDATE, "message": {**PRIVATE_UPDATE["message"], "chat": {"id": 1, "type": "group"}}}
    bot = {**PRIVATE_UPDATE, "message": {**PRIVATE_UPDATE["message"], "from": {"id": 9, "is_bot": True}}}
    photo = {**PRIVATE_UPDATE, "message": {k: v for k, v in PRIVATE_UPDATE["message"].items() if k != "text"}}
    edited = {"update_id": 2, "edited_message": PRIVATE_UPDATE["message"]}
    for update in (group, bot, photo, edited, {"update_id": 3}):
        assert telegram.normalize(update) is None


WHATSAPP_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "contacts": [{"wa_id": "60123456789", "profile": {"name": "Raj"}}],
                        "messages": [
                            {"from": "60123456789", "id": "wamid.ABC", "timestamp": "1700000000",
                             "type": "text", "text": {"body": "Can someone call me this week?"}},
                            {"from": "60123456789", "id": "wamid.IMG", "timestamp": "1700000001", "type": "image"},
                        ],
                    },
                },
                {"field": "messages", "value": {"statuses": [{"id": "wamid.ABC", "status": "read"}]}},
            ]
        }
    ],
}


def test_whatsapp_normalizes_text_and_ignores_statuses_and_media():
    messages = whatsapp.normalize(WHATSAPP_PAYLOAD)
    assert len(messages) == 1
    assert messages[0].channel == "whatsapp" and messages[0].sender_id == "60123456789"
    assert messages[0].display_name == "Raj"
    assert messages[0].message_id == "wa-wamid.ABC"


def test_whatsapp_challenge_and_signature():
    ok = {"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "1234"}
    assert whatsapp.verify_challenge(ok, "tok") == "1234"
    assert whatsapp.verify_challenge({**ok, "hub.verify_token": "bad"}, "tok") is None
    assert whatsapp.verify_challenge(ok, None) is None

    body = json.dumps(WHATSAPP_PAYLOAD).encode()
    good = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
    assert whatsapp.verify_signature(body, good, "appsecret")
    assert not whatsapp.verify_signature(body, good, "other")
    assert not whatsapp.verify_signature(body + b"x", good, "appsecret")
    assert not whatsapp.verify_signature(body, None, "appsecret")
    assert not whatsapp.verify_signature(body, good, None)
