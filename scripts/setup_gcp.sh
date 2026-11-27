#!/usr/bin/env bash
# One-time Google Cloud setup: APIs, Firestore, the Pub/Sub topic and a debug subscription.
#   PROJECT=my-project ./scripts/setup_gcp.sh
set -euo pipefail

: "${PROJECT:?Set PROJECT to your Google Cloud project id}"
REGION="${REGION:-asia-southeast1}"
TOPIC="${TOPIC:-lead-events}"

gcloud config set project "$PROJECT"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  pubsub.googleapis.com

# Firestore in native mode. Pick a location near you; it cannot be changed later.
gcloud firestore databases create --location="$REGION" || echo "(Firestore database may already exist, continuing)"

gcloud pubsub topics create "$TOPIC" || echo "(topic may already exist, continuing)"
# A subscription so you can SEE the events: gcloud pubsub subscriptions pull "$TOPIC-debug" --auto-ack --limit=5
gcloud pubsub subscriptions create "$TOPIC-debug" --topic="$TOPIC" || echo "(subscription may already exist, continuing)"

# Let the service's runtime identity write to Firestore and publish to Pub/Sub.
# This is Cloud Run's default identity, the Compute Engine default service account.
# For production, create a dedicated service account with only these two roles.
NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SA="${NUMBER}-compute@developer.gserviceaccount.com"
for ROLE in roles/datastore.user roles/pubsub.publisher; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${SA}" --role="$ROLE" --condition=None >/dev/null
done

echo "Done. Next: copy env.example.yaml to env.yaml, fill it in, then run ./scripts/deploy.sh"
