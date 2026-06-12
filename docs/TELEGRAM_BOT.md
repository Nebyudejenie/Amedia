# Telegram Bot — Setup & Operations

## 1. Create the bot
1. Message **@BotFather** → `/newbot` → pick a name + username
2. Copy the token into your server `.env` as `TELEGRAM_BOT_TOKEN`

## 2. Register the webhook
```bash
TELEGRAM_BOT_TOKEN=123:ABC ./scripts/setup-telegram-webhook.sh https://arada.fun
# prints the generated TELEGRAM_WEBHOOK_SECRET — add it to the server .env
```
The script registers `POST /webhooks/telegram` with a `secret_token`; Telegram
echoes it back as `X-Telegram-Bot-Api-Secret-Token` and the handler rejects
anything else with 403 (constant-time compare). It also installs the command
menu (start/submit/status/stats/settings/help).

## 3. Apply migration 016
```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U arada -d arada < db/migrations/016_telegram.sql
```

## Account linking flow
```
User → /start → bot stores 6-char token (15-min TTL, unambiguous alphabet)
     → user opens https://arada.fun/link?token=XXXXXX (logged in)
     → POST /api/v1/telegram/link binds telegram_user_id to the account
     → bot confirms "🎉 Account linked!" in the chat
```
One Telegram account links to one Arada account (409 otherwise).
Unlink: `DELETE /api/v1/telegram/link` or from settings.

Commands
| Command | Behavior |
|---|---|
| `/start` | Linking token + URL (or "already linked") |
| `/submit <url> #tags` | Validates URL (same SSRF guard as webhooks), dedupes by SHA256, 10/hour rate limit, replies with 🗑/📊 inline buttons |
| `/status` | Last 5 submissions with ⏳/🔍/✅/⚠️ + sentiment when complete |
| `/stats` | Totals + submissions remaining this hour |
| `/settings` | Masked email, linked date, dashboard link |
| `/help` / unknown | Command list |

## Security notes
- Webhook is **exempt from the generic API rate limiter** (it has its own
  secret-token auth and Telegram can burst); per-user submit limiting is
  enforced in the DB (10/hour, configurable via TELEGRAM_SUBMIT_LIMIT_PER_HOUR).
- Bot token only ever read from env; send errors log the exception type only.
- Emails are masked in /settings; tokens never appear in chat messages.
- Submissions land in `content.telegram_submissions` (status pipeline:
  pending → analyzing → complete/error); `notify_analysis_complete()` pushes
  the result back to the originating chat.
