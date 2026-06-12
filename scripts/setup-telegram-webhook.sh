#!/usr/bin/env bash
# Register the Arada webhook with Telegram.
# Usage: TELEGRAM_BOT_TOKEN=... ./scripts/setup-telegram-webhook.sh https://arada.fun
set -euo pipefail

BASE_URL="${1:?Usage: setup-telegram-webhook.sh <https://your-domain>}"
: "${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN (from @BotFather)}"

SECRET="${TELEGRAM_WEBHOOK_SECRET:-$(openssl rand -hex 32)}"

echo "→ Registering webhook ${BASE_URL}/webhooks/telegram"
curl -sf "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${BASE_URL}/webhooks/telegram" \
  -d "secret_token=${SECRET}" \
  -d 'allowed_updates=["message","callback_query"]' | python3 -m json.tool

echo "→ Registering command menu"
curl -sf "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setMyCommands" \
  -H 'Content-Type: application/json' \
  -d '{"commands":[
    {"command":"start","description":"Link your Arada account"},
    {"command":"submit","description":"Submit a URL for analysis"},
    {"command":"status","description":"Your last 5 submissions"},
    {"command":"stats","description":"Your usage totals"},
    {"command":"settings","description":"Account settings"},
    {"command":"help","description":"Show commands"}]}' | python3 -m json.tool

echo ""
echo "✅ Webhook registered."
echo "   Add to your server .env:  TELEGRAM_WEBHOOK_SECRET=${SECRET}"
