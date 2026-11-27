#!/usr/bin/env bash
# Point your Telegram bot at the deployed service.
#   export TELEGRAM_BOT_TOKEN=...            (from @BotFather; never paste it into chat or a slide)
#   export TELEGRAM_WEBHOOK_SECRET=...       (the same value as in env.yaml)
#   export SERVICE_URL=https://...run.app
#   ./scripts/set_telegram_webhook.sh
set -euo pipefail

: "${TELEGRAM_BOT_TOKEN:?}" "${TELEGRAM_WEBHOOK_SECRET:?}" "${SERVICE_URL:?}"

# setWebhook pushes updates to our URL. secret_token comes back in the
# X-Telegram-Bot-Api-Secret-Token header, which the service checks.
# While a webhook is set, getUpdates does not work: it is one or the other.
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${SERVICE_URL%/}/webhooks/telegram\", \"secret_token\": \"${TELEGRAM_WEBHOOK_SECRET}\", \"allowed_updates\": [\"message\"]}"
echo
