# Money Coming In

A small, deployable pattern for turning unstructured customer messages into structured, qualified leads in real time. Built for a Google DevFest session.

```
Telegram / WhatsApp / HTTP -> Cloud Run (FastAPI)
   adapter -> Gemini extraction (schema-enforced JSON) -> gate (rules in code)
   -> Firestore (leads, messages) + Pub/Sub (events on qualify / recycle)
   -> live dashboard (server-sent events from Firestore)
```

- The model only **extracts facts** (intent, budget, decision-maker, urgency). A few lines of Python decide whether a lead is qualified.
- Valid JSON is not the same as valid facts, so the output is validated again with Pydantic.
- Events publish only on a **transition**, so Pub/Sub carries signal, not noise.
- The recycled-lead demo: a dormant lead messages again with a changed situation and is re-scored using its history.

## Run

See `STEPS.md` for the full copy-paste walkthrough. Quick local start:

```bash
uv sync && uv run pytest -q
INGEST_TOKEN=dev uv run uvicorn app.main:app --port 8080
```

## Layout

- `app/`: service (`schema`, `extract`, `gate`, `pipeline`, `store`, `events`, `adapters/`, `static/dashboard.html`)
- `scripts/`: simulate, seed, check_model, GCP setup, deploy, Telegram webhook
- `docs/`: AI Studio schema, production notes and scheduled-sweep sketch
- `tests/`: 33 tests using a scripted fake extractor (no network)

## Security notes

Webhooks verify their secret or signature. `/messages` needs `INGEST_TOKEN`. The dashboard is public and hides sender ids and names on the server, so use demo data only. Secrets go in `env.yaml` (git-ignored). Only private text messages are processed, `/start` shows a consent notice, and the bot sends a fixed acknowledgement, not AI chat.

## Status

Unit tests pass. Not yet exercised against live Gemini, Firestore, Pub/Sub, Telegram or WhatsApp: run `scripts/check_model.py` and a full dry run before presenting. The WhatsApp signature check follows Meta's documented scheme but should be verified against their current docs.
