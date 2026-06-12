#!/usr/bin/env bash
# Deploy the RSS worker + migration 015 to Proxmox.
# Usage: ./scripts/deploy-rss-worker.sh [host]
set -euo pipefail

HOST="${1:-192.168.1.200}"
SSH="ssh -i ~/.ssh/proxmox_deploy root@${HOST}"

echo "→ Pulling latest code on ${HOST}"
$SSH "cd /opt/arada && git pull"

echo "→ Applying migration 015 (rss_feeds, feed_articles)"
$SSH "cd /opt/arada && docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U arada -d arada" < db/migrations/015_rss_feeds.sql

echo "→ Rebuilding image + starting rss-worker"
$SSH "cd /opt/arada && docker compose -f docker-compose.prod.yml build rss-worker && \
  docker compose -f docker-compose.prod.yml up -d rss-worker api"

echo "→ Verifying"
$SSH "docker logs arada-rss-worker-prod --tail 5"
echo "✅ RSS worker deployed"
