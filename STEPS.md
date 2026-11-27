# Money Coming In: the step by step build

Copy and paste each block. Everything uses fictional demo data. Never paste real customer messages into the demo, and never show your keys on screen.

You need: a Google account, a Google Cloud project with billing, `gcloud` installed, [uv](https://docs.astral.sh/uv/getting-started/installation/) installed (it downloads the right Python for you), and a Telegram account.

## Step 1: Get a Gemini API key

Open Google AI Studio, create an API key, then in your terminal:

```bash
export GEMINI_API_KEY="paste-key-here"
```

## Step 2: Design the schema in AI Studio

In AI Studio, open a prompt, turn on structured output, and paste the schema from `docs/ai-studio-schema.json`. Paste a sample message from `app/demo_data.py` and run it. This is the same schema the code sends.

## Step 3: Run it locally

```bash
uv sync
uv run pytest -q
export INGEST_TOKEN="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(24))')"
echo "$INGEST_TOKEN"
uv run uvicorn app.main:app --port 8080
```

Open http://localhost:8080 for the dashboard (empty). In a second terminal, with the same `INGEST_TOKEN` and `GEMINI_API_KEY` exported:

```bash
uv run python -m scripts.check_model        # real model vs the six samples
uv run python -m scripts.simulate singles   # watch qualified leads appear
uv run python -m scripts.simulate conversation
```

Locally the service uses in-memory storage and logs events instead of publishing.

## Step 4: Google Cloud setup

A new terminal does not keep variables you exported earlier. Export `GEMINI_API_KEY` and `INGEST_TOKEN` again if you still need them there. To check a value, run `echo "$INGEST_TOKEN"`.

Then run the setup script:

```bash
export PROJECT="your-project-id"
./scripts/setup_gcp.sh
```

This enables the APIs, creates Firestore, creates the `lead-events` topic and a debug subscription, and lets the service write to both.

Note:  
If `gcloud --version` says "command not found", install the Google Cloud CLI, then open a new terminal window so it is on your PATH:

```bash
brew install --cask gcloud-cli
gcloud --version
```

Log in and choose your project:

```bash
gcloud auth login
gcloud config set project your-project-id
```

## Step 5: Deploy to Cloud Run

```bash
cp env.example.yaml env.yaml     # fill in values; env.yaml is git-ignored
./scripts/deploy.sh
```

The script prints the service URL. Open it: same dashboard, now live from Firestore.

## Step 6: Connect Telegram

Message @BotFather, send `/newbot`, copy the token. Then:

```bash
export TELEGRAM_BOT_TOKEN="..."          # keep off screen
export TELEGRAM_WEBHOOK_SECRET="..."     # same value as in env.yaml
export SERVICE_URL="https://your-service-url.run.app"
./scripts/set_telegram_webhook.sh
```

Send your bot `/start`, then a message such as: "Hi, looking to buy a 3-bedroom, budget around RM800k, I decide with my wife, need to move in 2 months." Watch it appear on the dashboard.

Note: 
https://shell.cloud.google.com/ if your computer blocks it


## Step 7: See the events

```bash
gcloud pubsub subscriptions pull lead-events-debug --auto-ack --limit=5
```

Only qualified and recycled leads publish an event. Weak leads stay on the dashboard but publish nothing.

## (Optional) Step 8: The recycled lead

Message your bot once, then find your lead privately and seed it as dormant:

```bash
export GOOGLE_CLOUD_PROJECT="$PROJECT"
gcloud auth application-default login
uv run python -m scripts.seed --list              # do this off screen: keys can include phone numbers
uv run python -m scripts.seed --key telegram:YOUR_ID
```

Now message the bot: "We got a bonus, budget is now RM45k..." The lead turns into a **recycled** card showing what changed.

## Troubleshooting

- `gcloud: command not found`: the Google Cloud CLI is not installed or the terminal is old. See Step 4.
- Nothing appears: check `gcloud run services logs read money-coming-in --region asia-southeast1`.
- Telegram 403 in logs: the webhook secret in `env.yaml` and in step 6 differ.
- Extraction 502: check `GEMINI_API_KEY` and the model name (`GEMINI_MODEL` overrides the default).

Production notes and the scheduled sweep: `docs/GOING_FURTHER.md`.
