# RSS Feed Integration

## Architecture

```
User → POST /api/v1/feeds (validates URL serves RSS/Atom)
            ↓
   content.rss_feeds (registry: status, errors, next_fetch_at)
            ↓
rss-worker (APScheduler, every RSS_FETCH_INTERVAL_MINUTES)
   • sweeps feeds WHERE is_active AND next_fetch_at <= now()
   • fetches up to RSS_BATCH_SIZE feeds in parallel (semaphore)
   • parses RSS 2.0 / Atom 1.0 via feedparser (encoding + bozo tolerant)
   • dedupes by SHA256(article_url) — ON CONFLICT DO NOTHING
            ↓
   content.feed_articles (deduplicated article store)
```

## Failure model

| Event | Behavior |
|---|---|
| Fetch/parse error | `error_count += 1`, `last_error` stored, next attempt delayed `interval × 2^errors` (capped 24 h) |
| 5 consecutive errors (`RSS_ERROR_THRESHOLD`) | feed disabled (`is_active=false`), CRITICAL log line for alerting |
| Successful fetch | `error_count` reset to 0, next run at normal interval |
| Re-enable via `PATCH {is_active: true}` | errors cleared, fetched immediately |
| Fetch slower than `RSS_SLOW_FETCH_ALERT_SECONDS` | WARNING log line |

## Configuration (env)

| Variable | Default | Meaning |
|---|---|---|
| `RSS_FETCH_INTERVAL_MINUTES` | 15 | Scheduler sweep cadence |
| `RSS_FETCH_TIMEOUT_SECONDS` | 30 | Per-feed HTTP timeout |
| `RSS_BATCH_SIZE` | 20 | Parallel fetches per sweep |
| `RSS_ERROR_THRESHOLD` | 5 | Consecutive errors before disable |
| `RSS_SLOW_FETCH_ALERT_SECONDS` | 5 | Slow-fetch warning threshold |

Per-feed `refresh_interval_minutes` (5–1440) overrides the global cadence —
the sweep only picks feeds whose `next_fetch_at` is due, so 1000+ feeds with
mixed intervals are fine: each sweep is O(due feeds), parallelized 20 at a time.

## Endpoints (all require Bearer auth)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/feeds` | Register feed (400 if URL isn't valid RSS/Atom, 409 if duplicate) |
| GET | `/api/v1/feeds` | List own feeds + article_count (paginated, X-Total-Count) |
| PATCH | `/api/v1/feeds/{id}` | Pause/resume, change interval (resume clears errors) |
| DELETE | `/api/v1/feeds/{id}` | Remove feed + articles (CASCADE) |
| GET | `/api/v1/feeds/{id}/articles` | Paginated articles, newest first |
| POST | `/api/v1/feeds/{id}/fetch` | Manual immediate fetch |

## Metrics (Prometheus, exposed on /metrics)

- `rss_feeds_processed_total{result="success|error"}`
- `rss_articles_found_total` / `rss_duplicates_skipped_total`
- `rss_fetch_duration_seconds` (histogram)

Suggested alerts: error rate > 20% over 1 h; p95 fetch duration > 5 s;
any `RSS feed DISABLED` critical log line.

## Deploy

```bash
./scripts/deploy-rss-worker.sh 192.168.1.200
```

Applies migration 015, rebuilds the image, and starts the `rss-worker`
container alongside the API.
