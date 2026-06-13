"""Article → video generation pipeline.

Stages: script (Ollama) → images (Unsplash) → audio (gTTS) → compose (FFmpeg)
→ upload (MinIO). Each stage updates content.videos.stage so the frontend can
show progress. External tools (ffmpeg/ffprobe/gtts/Ollama/Unsplash) are isolated
behind small functions; the orchestration logic and all command-building are
pure and unit-tested without them.

Design notes:
  • Captions are burned in via a generated .srt + ffmpeg `subtitles` filter
    (cleaner and more testable than chained drawtext).
  • Images are shown via the concat demuxer with a per-image duration derived
    from the narration length, clamped to 6–8s as specified.
"""
import asyncio
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from clients import MinIOClient, OllamaClient, PostgreSQLPool
from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_MODEL = os.getenv("VIDEO_SCRIPT_MODEL", "mistral")
UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")

VIDEO_BUCKET = f"{settings.minio_bucket_prefix}-videos"
MIN_SECONDS_PER_IMAGE = 6.0
MAX_SECONDS_PER_IMAGE = 8.0
TARGET_IMAGE_COUNT = 8
CAPTION_MAX_CHARS = 90
SLOW_GENERATION_ALERT_SECONDS = int(os.getenv("VIDEO_SLOW_ALERT_SECONDS", "300"))
MAX_ATTEMPTS = int(os.getenv("VIDEO_MAX_ATTEMPTS", "3"))

# Royalty-free bed; optional. Absent → no music track (pipeline still works).
BACKGROUND_MUSIC_PATH = os.getenv("VIDEO_BG_MUSIC_PATH", "")

TONE_GUIDANCE = {
    "professional": "Use a polished, authoritative broadcast-news tone.",
    "casual": "Use a warm, conversational tone, like explaining to a friend.",
    "educational": "Use a clear, instructive tone that teaches the topic step by step.",
}

# Words narrators speak per minute → used to estimate duration before TTS
WORDS_PER_MINUTE = 150


class VideoError(Exception):
    """Any unrecoverable pipeline failure (message is safe for storage)."""


@dataclass
class Assets:
    """Working files for one generation, all under a temp dir."""

    workdir: str
    script: str = ""
    image_paths: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    audio_path: str = ""
    srt_path: str = ""
    output_path: str = ""
    duration: int = 0


# ===========================================================================
# Pure helpers (unit-tested without any external tool)
# ===========================================================================

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "this", "that", "these", "those",
    "it", "its", "as", "at", "by", "from", "has", "have", "had", "will", "would",
    "can", "could", "should", "their", "they", "you", "your", "we", "our",
}


def extract_keywords(title: str, content: str, limit: int = 4) -> list[str]:
    """Most frequent meaningful words → Unsplash search terms.

    Title words are weighted higher (they define the subject).
    """
    text = f"{title} {title} {content}".lower()
    words = re.findall(r"[a-z][a-z'-]{2,}", text)
    freq: dict[str, int] = {}
    for w in words:
        if w in _STOPWORDS:
            continue
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq, key=lambda w: (-freq[w], w))
    return ranked[:limit] or ["news"]


def clean_script(raw: str) -> str:
    """Strip LLM artifacts: stage directions, markdown, 'Script:' preambles."""
    text = raw.strip()
    # Drop a leading label line like "Narration:" / "Script:"
    text = re.sub(r"^\s*(script|narration|voiceover)\s*:\s*", "", text, flags=re.I)
    # Remove bracketed visual cues [shot of ...], (pause), and markdown emphasis
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"\((?:pause|beat|music)[^)]*\)", "", text, flags=re.I)
    text = re.sub(r"[*_#`]+", "", text)
    # Collapse whitespace
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def estimate_duration_seconds(script: str) -> int:
    """Narration length from word count (before TTS runs)."""
    words = len(script.split())
    return max(1, round(words / WORDS_PER_MINUTE * 60))


def seconds_per_image(total_duration: float, n_images: int) -> float:
    """Per-image hold time, clamped to the 6–8s spec window."""
    if n_images <= 0:
        return MAX_SECONDS_PER_IMAGE
    raw = total_duration / n_images
    return max(MIN_SECONDS_PER_IMAGE, min(MAX_SECONDS_PER_IMAGE, raw))


def images_needed(total_duration: float) -> int:
    """How many images to cover the narration at ~7s each, within [3, 12]."""
    n = round(total_duration / ((MIN_SECONDS_PER_IMAGE + MAX_SECONDS_PER_IMAGE) / 2))
    return max(3, min(12, n))


def chunk_captions(script: str, max_chars: int = CAPTION_MAX_CHARS) -> list[str]:
    """Split narration into caption-sized lines on sentence/word boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", script.strip())
    chunks: list[str] = []
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            chunks.append(sentence.strip())
            continue
        # Long sentence: wrap on words
        current = ""
        for word in sentence.split():
            if len(current) + len(word) + 1 > max_chars:
                if current:
                    chunks.append(current.strip())
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            chunks.append(current.strip())
    return chunks


def _srt_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(captions: list[str], total_duration: float) -> str:
    """Even time-slicing of captions across the narration → SRT text."""
    if not captions:
        return ""
    per = total_duration / len(captions)
    blocks = []
    for i, text in enumerate(captions):
        start = _srt_timestamp(i * per)
        end = _srt_timestamp(min(total_duration, (i + 1) * per))
        blocks.append(f"{i + 1}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks)


def build_concat_file(image_paths: list[str], per_image: float) -> str:
    """ffmpeg concat-demuxer playlist holding each image for `per_image` seconds.

    The last image is repeated without a duration line (concat demuxer quirk:
    the final entry needs a trailing `file` to honor the preceding duration).
    """
    lines: list[str] = []
    for path in image_paths:
        lines.append(f"file '{path}'")
        lines.append(f"duration {per_image:.3f}")
    if image_paths:
        lines.append(f"file '{image_paths[-1]}'")
    return "\n".join(lines) + "\n"


def build_ffmpeg_command(
    concat_path: str,
    audio_path: str,
    srt_path: str,
    output_path: str,
    music_path: str = "",
) -> list[str]:
    """Assemble the H.264 1080p render command (pure; no execution).

    - images via concat demuxer, scaled/padded to 1920x1080 @30fps
    - fade in/out + burned-in captions (subtitles filter)
    - narration always present; optional ducked background music mixed under it
    - -shortest so the video ends with the audio
    """
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_path,
           "-i", audio_path]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", music_path]

    # Escape the srt path for the filter graph (colons/commas are special)
    srt_escaped = srt_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    vf = (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
        "fps=30,format=yuv420p,"
        f"subtitles='{srt_escaped}':force_style='Fontsize=22,Alignment=2,"
        "MarginV=40,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=4'"
    )

    if music_path:
        # Mix narration (1.0) with quiet looped music (0.12), end at narration
        filter_complex = (
            f"[0:v]{vf}[v];"
            "[2:a]volume=0.12[bg];"
            "[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
        cmd += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", vf, "-map", "0:v", "-map", "1:a"]

    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-shortest", "-movflags", "+faststart", output_path,
    ]
    return cmd


def backoff_seconds(attempt: int) -> int:
    """Retry backoff: 30s, 60s, 120s… capped at 10 min."""
    return min(600, 30 * (2 ** max(0, attempt - 1)))


# ===========================================================================
# Stage 1 — script (Ollama)
# ===========================================================================


async def generate_script(title: str, content: str, tone: str) -> str:
    """Convert an article into a ~90-second (300–400 word) narration."""
    guidance = TONE_GUIDANCE.get(tone, TONE_GUIDANCE["professional"])
    prompt = (
        "You are a professional video scriptwriter. Convert the article below "
        "into a single spoken-narration script for a 90-second video.\n"
        f"{guidance}\n"
        "Rules: 300-400 words. Plain spoken sentences only — no headings, no "
        "stage directions, no bullet points, no camera cues. Start with a hook.\n\n"
        f"TITLE: {title}\n\nARTICLE:\n{content[:4000]}\n\nSCRIPT:"
    )
    try:
        raw = await OllamaClient.generate(model=OLLAMA_MODEL, prompt=prompt)
    except Exception as e:
        raise VideoError(f"script generation failed: {type(e).__name__}")

    script = clean_script(raw)
    if len(script.split()) < 40:
        raise VideoError("script too short — LLM returned insufficient text")
    return script


# ===========================================================================
# Stage 2 — images (Unsplash, with graceful fallback)
# ===========================================================================


async def fetch_image_urls(keywords: list[str], count: int) -> list[str]:
    """Query Unsplash for landscape photos. Empty list if unconfigured/empty."""
    if not UNSPLASH_KEY:
        logger.warning("UNSPLASH_ACCESS_KEY unset — falling back to color frames")
        return []

    query = " ".join(keywords)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": count, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
    except Exception as e:
        logger.warning(f"Unsplash fetch failed ({type(e).__name__}) — color frames")
        return []

    return [r["urls"]["regular"] for r in results if r.get("urls", {}).get("regular")]


async def download_images(urls: list[str], workdir: str) -> list[str]:
    """Download image URLs to disk. Skips failures; returns local paths."""
    paths: list[str] = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for i, url in enumerate(urls):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                path = os.path.join(workdir, f"img_{i:02d}.jpg")
                with open(path, "wb") as f:
                    f.write(resp.content)
                paths.append(path)
            except Exception:
                logger.warning(f"image {i} download failed — skipping")
    return paths


def make_color_frames(workdir: str, count: int) -> list[str]:
    """Fallback when no images: solid 1080p frames via ffmpeg lavfi.

    Generated synchronously (fast). Colors cycle through a calm palette.
    """
    import subprocess

    palette = ["#1e293b", "#0f172a", "#334155", "#1e3a5f", "#0c4a6e",
               "#164e63", "#1e293b", "#312e81"]
    paths: list[str] = []
    for i in range(count):
        color = palette[i % len(palette)]
        path = os.path.join(workdir, f"frame_{i:02d}.png")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"color=c={color}:s=1920x1080", "-frames:v", "1", path],
            check=True, capture_output=True, timeout=30,
        )
        paths.append(path)
    return paths


def ensure_image_count(paths: list[str], needed: int) -> list[str]:
    """Cycle the available images to reach `needed` (handles too-few results)."""
    if not paths:
        return []
    if len(paths) >= needed:
        return paths[:needed]
    return [paths[i % len(paths)] for i in range(needed)]


# ===========================================================================
# Stage 3 — audio (gTTS; ElevenLabs optional)
# ===========================================================================


def _synthesize_gtts(script: str, out_path: str) -> None:
    """Blocking gTTS call (run via asyncio.to_thread)."""
    from gtts import gTTS

    gTTS(text=script, lang="en", slow=False).save(out_path)


async def synthesize_speech(script: str, out_path: str, voice: str = "female") -> None:
    """Render narration MP3. Prefers ElevenLabs when keyed, else gTTS."""
    if ELEVENLABS_KEY:
        try:
            await _synthesize_elevenlabs(script, out_path, voice)
            return
        except Exception as e:
            logger.warning(f"ElevenLabs failed ({type(e).__name__}) — gTTS fallback")
    try:
        await asyncio.to_thread(_synthesize_gtts, script, out_path)
    except Exception as e:
        raise VideoError(f"text-to-speech failed: {type(e).__name__}")


async def _synthesize_elevenlabs(script: str, out_path: str, voice: str) -> None:
    voice_id = {"female": "21m00Tcm4TlvDq8ikWAM", "male": "VR6AewLTigWG4xSOukaG"}.get(
        voice, "21m00Tcm4TlvDq8ikWAM"
    )
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": ELEVENLABS_KEY},
            json={"text": script, "model_id": "eleven_monolingual_v1"},
        )
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)


# ===========================================================================
# Stage 4 — compose (FFmpeg) + probe
# ===========================================================================


def probe_duration(media_path: str) -> float:
    """Seconds of an audio/video file via ffprobe."""
    import subprocess

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", media_path],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return float(out.stdout.strip())


def run_ffmpeg(cmd: list[str], timeout: int = 600) -> None:
    """Execute an ffmpeg command, surfacing stderr tail on failure."""
    import subprocess

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-3:] if proc.stderr else []
        raise VideoError(f"ffmpeg failed: {' | '.join(tail) or 'unknown error'}")


def compose_video(assets: Assets) -> None:
    """Build concat list + SRT, render the MP4 into assets.output_path."""
    per_image = seconds_per_image(assets.duration, len(assets.image_paths))
    concat_path = os.path.join(assets.workdir, "playlist.txt")
    with open(concat_path, "w") as f:
        f.write(build_concat_file(assets.image_paths, per_image))

    captions = chunk_captions(assets.script)
    assets.srt_path = os.path.join(assets.workdir, "captions.srt")
    with open(assets.srt_path, "w") as f:
        f.write(build_srt(captions, assets.duration))

    assets.output_path = os.path.join(assets.workdir, "video.mp4")
    music = BACKGROUND_MUSIC_PATH if BACKGROUND_MUSIC_PATH and os.path.exists(
        BACKGROUND_MUSIC_PATH
    ) else ""
    cmd = build_ffmpeg_command(
        concat_path, assets.audio_path, assets.srt_path, assets.output_path, music
    )
    run_ffmpeg(cmd)


# ===========================================================================
# Upload
# ===========================================================================


def upload_video(video_id: str, output_path: str) -> tuple[str, str, float]:
    """Push the MP4 to MinIO. Returns (bucket, key, size_mb)."""
    MinIOClient.make_bucket(VIDEO_BUCKET)
    key = f"{video_id}.mp4"
    MinIOClient.put_file(VIDEO_BUCKET, key, output_path, "video/mp4")
    size_mb = round(os.path.getsize(output_path) / (1024 * 1024), 2)
    return VIDEO_BUCKET, key, size_mb


# ===========================================================================
# DB helpers
# ===========================================================================


async def _set_stage(video_id: str, stage: str, status: str = "generating") -> None:
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            "UPDATE content.videos SET stage = $2, status = $3, updated_at = now() "
            "WHERE id = $1",
            video_id, stage, status,
        )


async def _record_timing(video_id: str, stage: str, seconds: float) -> None:
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            "UPDATE content.videos SET stage_timings = stage_timings || $2::jsonb "
            "WHERE id = $1",
            video_id, f'{{"{stage}": {seconds:.1f}}}',
        )


# ===========================================================================
# Orchestrator
# ===========================================================================


async def produce_video(video_id: str) -> None:
    """Run the full pipeline for one queued video row.

    Updates stage/status as it goes; on success marks complete with metadata,
    on failure records the error and lets the worker decide on retry. Raises
    VideoError so the worker can count the attempt.
    """
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT v.id, v.title, v.tone, v.voice, v.article_id,
                   a.title AS article_title, a.description AS article_body
            FROM content.videos v
            LEFT JOIN content.feed_articles a ON a.id = v.article_id
            WHERE v.id = $1
            """,
            video_id,
        )
    if not row:
        raise VideoError("video row not found")

    title = row["article_title"] or row["title"]
    body = row["article_body"] or row["title"]
    started = time.monotonic()
    timings: dict[str, float] = {}

    with tempfile.TemporaryDirectory(prefix=f"vid_{video_id[:8]}_") as workdir:
        assets = Assets(workdir=workdir)

        # --- script ---
        await _set_stage(video_id, "script")
        t = time.monotonic()
        assets.script = await generate_script(title, body, row["tone"])
        timings["script"] = time.monotonic() - t
        await _record_timing(video_id, "script", timings["script"])

        # --- images ---
        await _set_stage(video_id, "images")
        t = time.monotonic()
        est = estimate_duration_seconds(assets.script)
        need = images_needed(est)
        keywords = extract_keywords(title, body)
        urls = await fetch_image_urls(keywords, max(TARGET_IMAGE_COUNT, need))
        assets.image_urls = urls
        downloaded = await download_images(urls, workdir) if urls else []
        if not downloaded:
            downloaded = await asyncio.to_thread(make_color_frames, workdir, need)
        assets.image_paths = ensure_image_count(downloaded, need)
        if not assets.image_paths:
            raise VideoError("no images available after fallback")
        timings["images"] = time.monotonic() - t
        await _record_timing(video_id, "images", timings["images"])

        # --- audio ---
        await _set_stage(video_id, "audio")
        t = time.monotonic()
        assets.audio_path = os.path.join(workdir, "narration.mp3")
        await synthesize_speech(assets.script, assets.audio_path, row["voice"])
        assets.duration = round(await asyncio.to_thread(probe_duration, assets.audio_path))
        timings["audio"] = time.monotonic() - t
        await _record_timing(video_id, "audio", timings["audio"])

        # --- compose ---
        await _set_stage(video_id, "compose")
        t = time.monotonic()
        await asyncio.to_thread(compose_video, assets)
        timings["compose"] = time.monotonic() - t
        await _record_timing(video_id, "compose", timings["compose"])

        # --- upload ---
        await _set_stage(video_id, "upload")
        t = time.monotonic()
        bucket, key, size_mb = await asyncio.to_thread(
            upload_video, video_id, assets.output_path
        )
        timings["upload"] = time.monotonic() - t
        await _record_timing(video_id, "upload", timings["upload"])

    total = round(time.monotonic() - started)
    if total > SLOW_GENERATION_ALERT_SECONDS:
        logger.warning(
            f"SLOW video generation: {video_id} took {total}s "
            f"(>{SLOW_GENERATION_ALERT_SECONDS}s) timings={timings}"
        )

    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            """
            UPDATE content.videos
            SET status = 'complete', stage = 'done',
                script = $2, image_urls = $3,
                duration_seconds = $4, file_size_mb = $5,
                minio_bucket = $6, minio_key = $7,
                generation_time_seconds = $8, error_message = NULL,
                updated_at = now()
            WHERE id = $1
            """,
            video_id, assets.script, assets.image_urls, assets.duration,
            size_mb, bucket, key, total,
        )
    logger.info(f"Video complete: {video_id} ({assets.duration}s, {size_mb}MB, {total}s)")
