# Video Generation — Architecture & Operations

Turns an article into a narrated ~90-second MP4 (1080p, H.264).

## Pipeline

```
POST /api/v1/videos/generate  →  content.videos row (status=queued)
                                       │
            video-worker claims it (FOR UPDATE SKIP LOCKED, up to N at once)
                                       │
   script ─► images ─► audio ─► compose ─► upload      (stage column updates)
  (Ollama)  (Unsplash) (gTTS)   (FFmpeg)   (MinIO)
                                       │
                          status=complete, presigned playback URL
```

Each stage writes `content.videos.stage`, which the frontend polls via
`GET /api/v1/videos/{id}` to drive the progress bar:
`queued → script → images → audio → compose → upload → done`.

### Stages

| Stage | Tool | Fallback / edge handling |
|---|---|---|
| Script | Ollama (`VIDEO_SCRIPT_MODEL`, default `mistral`) | Rejects <40-word output; LLM error → `VideoError` (retried) |
| Images | Unsplash search API | No API key or API failure → solid-color 1080p frames via ffmpeg lavfi; too-few results cycled to fill |
| Audio | gTTS (default) or ElevenLabs (`ELEVENLABS_API_KEY`) | ElevenLabs failure → gTTS; gTTS failure → `VideoError` |
| Compose | FFmpeg | Images via concat demuxer (6–8s each, derived from narration length); captions burned in from a generated `.srt`; optional ducked background music (`VIDEO_BG_MUSIC_PATH`) |
| Upload | MinIO (`<prefix>-videos` bucket) | Playback via 1-hour presigned URL |

## Job queue & retries

`video-worker` (standalone container) polls every `VIDEO_POLL_SECONDS`,
claims up to `VIDEO_CONCURRENCY` queued rows atomically (`SKIP LOCKED`, so
multiple replicas are safe), and runs them under a concurrency semaphore.
Each attempt increments `attempts` up-front. On failure it re-queues with
exponential backoff (30s → 60s → 120s, capped 10 min) until
`VIDEO_MAX_ATTEMPTS` (default 3), then marks `status=failed` with the error.

## Monitoring

- Per-stage timings stored in `content.videos.stage_timings` (JSONB).
- `generation_time_seconds` recorded on completion.
- Generations exceeding `VIDEO_SLOW_ALERT_SECONDS` (default 300 = the 5-min
  target) log a `SLOW video generation` warning with the stage breakdown.
- All failures log with the stage and a safe error message.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | /api/v1/videos/generate | `{article_id?, title?, tone, voice}`; 202 + `video_id`; counts against the plan's monthly quota |
| GET | /api/v1/videos | Paginated list (`X-Total-Count`) with playback URLs |
| GET | /api/v1/videos/{id} | Full metadata incl. script, image_urls, progress |
| DELETE | /api/v1/videos/{id} | Removes row + MinIO object |

`tone` ∈ professional|casual|educational · `voice` ∈ female|male.

## Deployment

1. The runtime image now installs **ffmpeg** (Dockerfile.prod). Rebuild it.
2. Apply migration 018:
   ```bash
   docker compose -f docker-compose.prod.yml exec -T postgres \
     psql -U arada -d arada < db/migrations/018_videos.sql
   ```
3. Set env (server `.env`): `UNSPLASH_ACCESS_KEY` (free at unsplash.com/developers),
   optionally `ELEVENLABS_API_KEY`, and ensure Ollama has the script model:
   `ollama pull mistral`.
4. Start the worker: `docker compose -f docker-compose.prod.yml up -d video-worker`.

## Performance

Target <5 min/video. Dominant costs are Ollama (script) and FFmpeg (compose);
both run off the request path in the worker. Throughput scales with
`VIDEO_CONCURRENCY` and the number of `video-worker` replicas.

## Notes / scope

- The prompt sketched a SERIAL/INT `videos` table; it was adapted to the
  codebase's UUID-PK + schema-qualified convention (`content.videos`).
- "Share YouTube link" in the spec is represented by the copy-link button over
  the presigned MinIO URL; actual YouTube upload is out of scope here.
