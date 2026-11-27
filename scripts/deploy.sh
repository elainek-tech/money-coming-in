#!/usr/bin/env bash
# Build from source and deploy to Cloud Run. Reads settings from env.yaml (git-ignored).
#   PROJECT=my-project ./scripts/deploy.sh
set -euo pipefail

: "${PROJECT:?Set PROJECT to your Google Cloud project id}"
REGION="${REGION:-asia-southeast1}"
[ -f env.yaml ] || { echo "Create env.yaml first: cp env.example.yaml env.yaml, then fill it in."; exit 1; }

# --allow-unauthenticated: Telegram and Meta must be able to reach the webhooks. The webhooks and
#   /messages check their own secrets. The dashboard at / is public, so only demo data belongs here.
# --max-instances 3: a cost ceiling while attendees are sending messages.
# --timeout 3600: the dashboard keeps one long-lived connection open per viewer.
gcloud run deploy money-coming-in \
  --project "$PROJECT" \
  --region "$REGION" \
  --source . \
  --allow-unauthenticated \
  --max-instances 3 \
  --timeout 3600 \
  --env-vars-file env.yaml

gcloud run services describe money-coming-in --project "$PROJECT" --region "$REGION" --format='value(status.url)'
