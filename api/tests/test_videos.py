"""Tests for the video generation pipeline: pure helpers, stages, worker, API."""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import app
from auth.jwt_handler import create_access_token
from services import video_service as vs

client = TestClient(app)


def auth_header(user_id=None) -> dict:
    token = create_access_token(user_id=str(user_id or uuid4()), email="v@example.com")
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Pure helpers
# ===========================================================================


class TestKeywordsAndScript:
    @pytest.mark.unit
    def test_keywords_rank_by_frequency_and_weight_title(self):
        kws = vs.extract_keywords(
            "Ethiopia Coffee Exports",
            "Coffee exports rose sharply. Coffee farmers celebrated the harvest.",
            limit=3,
        )
        assert "coffee" in kws
        assert all(k not in vs._STOPWORDS for k in kws)

    @pytest.mark.unit
    def test_keywords_fallback_when_empty(self):
        assert vs.extract_keywords("", "") == ["news"]

    @pytest.mark.unit
    def test_clean_script_strips_artifacts(self):
        raw = "Script: [wide shot] Welcome to the **news**. (pause) Here's _why_ it matters.\n#tag"
        cleaned = vs.clean_script(raw)
        assert "[" not in cleaned and "]" not in cleaned
        assert "*" not in cleaned and "_" not in cleaned and "#" not in cleaned
        assert not cleaned.lower().startswith("script:")
        assert "(pause)" not in cleaned
        assert "Welcome to the news" in cleaned

    @pytest.mark.unit
    def test_estimate_duration_from_wordcount(self):
        script = " ".join(["word"] * 150)  # 150 wpm → ~60s
        assert vs.estimate_duration_seconds(script) == 60


class TestTimingMath:
    @pytest.mark.unit
    def test_seconds_per_image_clamped(self):
        assert vs.seconds_per_image(90, 3) == vs.MAX_SECONDS_PER_IMAGE   # 30 → 8
        assert vs.seconds_per_image(90, 30) == vs.MIN_SECONDS_PER_IMAGE  # 3 → 6
        assert vs.seconds_per_image(70, 10) == 7.0                       # in range
        assert vs.seconds_per_image(90, 0) == vs.MAX_SECONDS_PER_IMAGE

    @pytest.mark.unit
    def test_images_needed_bounds(self):
        assert vs.images_needed(90) == 13 - 0 or vs.images_needed(90) <= 12
        assert 3 <= vs.images_needed(5) <= 12
        assert vs.images_needed(1000) == 12  # capped
        assert vs.images_needed(1) == 3      # floored

    @pytest.mark.unit
    def test_ensure_image_count_cycles_and_truncates(self):
        assert vs.ensure_image_count(["a", "b"], 5) == ["a", "b", "a", "b", "a"]
        assert vs.ensure_image_count(["a", "b", "c"], 2) == ["a", "b"]
        assert vs.ensure_image_count([], 5) == []

    @pytest.mark.unit
    def test_backoff_progression(self):
        assert vs.backoff_seconds(1) == 30
        assert vs.backoff_seconds(2) == 60
        assert vs.backoff_seconds(3) == 120
        assert vs.backoff_seconds(99) == 600  # capped at 10 min


class TestCaptionsAndSrt:
    @pytest.mark.unit
    def test_chunk_captions_respects_max(self):
        script = "Short one. " + "word " * 60 + ". Another short sentence."
        chunks = vs.chunk_captions(script, max_chars=40)
        assert all(len(c) <= 40 for c in chunks)
        assert len(chunks) >= 2

    @pytest.mark.unit
    def test_srt_timestamps_and_order(self):
        srt = vs.build_srt(["Line one", "Line two"], total_duration=10)
        assert "00:00:00,000 --> 00:00:05,000" in srt
        assert "00:00:05,000 --> 00:00:10,000" in srt
        assert srt.index("Line one") < srt.index("Line two")

    @pytest.mark.unit
    def test_srt_empty_when_no_captions(self):
        assert vs.build_srt([], 10) == ""

    @pytest.mark.unit
    def test_srt_timestamp_format(self):
        assert vs._srt_timestamp(3661.5) == "01:01:01,500"


class TestFfmpegCommand:
    @pytest.mark.unit
    def test_concat_file_repeats_last_frame(self):
        out = vs.build_concat_file(["/a.jpg", "/b.jpg"], 6.5)
        lines = out.strip().split("\n")
        # two files + two durations + trailing repeat of last file
        assert lines[0] == "file '/a.jpg'"
        assert lines[1] == "duration 6.500"
        assert lines[-1] == "file '/b.jpg'"

    @pytest.mark.unit
    def test_concat_file_empty(self):
        assert vs.build_concat_file([], 6.0) == "\n"

    @pytest.mark.unit
    def test_command_without_music(self):
        cmd = vs.build_ffmpeg_command("/c.txt", "/a.mp3", "/c.srt", "/out.mp4")
        assert cmd[0] == "ffmpeg"
        assert "/out.mp4" == cmd[-1]
        assert "libx264" in cmd and "aac" in cmd
        assert "-shortest" in cmd
        # one audio input only → simple -vf path, mapped streams
        assert "-vf" in cmd
        assert "-map" in cmd
        assert "+faststart" in cmd

    @pytest.mark.unit
    def test_command_with_music_uses_amix(self):
        cmd = vs.build_ffmpeg_command("/c.txt", "/a.mp3", "/c.srt", "/o.mp4", "/music.mp3")
        joined = " ".join(cmd)
        assert "amix=inputs=2" in joined
        assert "filter_complex" in joined
        assert "-stream_loop" in cmd  # music looped to cover the narration

    @pytest.mark.unit
    def test_command_escapes_subtitle_path(self):
        cmd = vs.build_ffmpeg_command("/c.txt", "/a.mp3", "/tmp/x:y.srt", "/o.mp4")
        joined = " ".join(cmd)
        # the colon in the srt path must be escaped inside the filter
        assert "x\\:y.srt" in joined


# ===========================================================================
# Stages (externals mocked)
# ===========================================================================


class TestScriptStage:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_script_cleans_output(self):
        long_script = "Script: " + "This is a sentence. " * 30
        with patch.object(vs.OllamaClient, "generate", new=AsyncMock(return_value=long_script)):
            result = await vs.generate_script("Title", "Body content", "professional")
        assert not result.lower().startswith("script:")
        assert len(result.split()) >= 40

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_script_rejects_too_short(self):
        with patch.object(vs.OllamaClient, "generate", new=AsyncMock(return_value="Too short.")):
            with pytest.raises(vs.VideoError, match="too short"):
                await vs.generate_script("T", "B", "casual")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_script_wraps_ollama_failure(self):
        with patch.object(vs.OllamaClient, "generate", new=AsyncMock(side_effect=RuntimeError("down"))):
            with pytest.raises(vs.VideoError, match="script generation failed"):
                await vs.generate_script("T", "B", "educational")


class TestImageStage:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_unsplash_key_returns_empty(self):
        with patch.object(vs, "UNSPLASH_KEY", ""):
            assert await vs.fetch_image_urls(["coffee"], 8) == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unsplash_results_parsed(self):
        payload = {"results": [
            {"urls": {"regular": "https://img/1.jpg"}},
            {"urls": {"regular": "https://img/2.jpg"}},
            {"urls": {}},  # malformed entry skipped
        ]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        with patch.object(vs, "UNSPLASH_KEY", "key"), \
             patch.object(vs.httpx, "AsyncClient") as ac:
            ac.return_value.__aenter__.return_value = mock_client
            urls = await vs.fetch_image_urls(["coffee"], 8)
        assert urls == ["https://img/1.jpg", "https://img/2.jpg"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unsplash_failure_degrades_gracefully(self):
        with patch.object(vs, "UNSPLASH_KEY", "key"), \
             patch.object(vs.httpx, "AsyncClient", side_effect=RuntimeError("network")):
            assert await vs.fetch_image_urls(["x"], 5) == []


class TestAudioStage:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_gtts_used_when_no_elevenlabs(self):
        with patch.object(vs, "ELEVENLABS_KEY", ""), \
             patch.object(vs.asyncio, "to_thread", new=AsyncMock()) as tt:
            await vs.synthesize_speech("hello world", "/tmp/out.mp3", "female")
        tt.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tts_failure_raises_videoerror(self):
        with patch.object(vs, "ELEVENLABS_KEY", ""), \
             patch.object(vs.asyncio, "to_thread", new=AsyncMock(side_effect=RuntimeError("boom"))):
            with pytest.raises(vs.VideoError, match="text-to-speech failed"):
                await vs.synthesize_speech("hi", "/tmp/x.mp3")


class TestCompose:
    @pytest.mark.unit
    def test_run_ffmpeg_raises_on_nonzero(self):
        fake = MagicMock(returncode=1, stderr="line1\nline2\nboom")
        with patch.object(vs, "__name__", vs.__name__), \
             patch("subprocess.run", return_value=fake):
            with pytest.raises(vs.VideoError, match="ffmpeg failed"):
                vs.run_ffmpeg(["ffmpeg", "-y"])


# ===========================================================================
# Worker: claim, retry, fail
# ===========================================================================


class TestWorker:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retry_requeues_with_backoff(self):
        from workers import video_worker as w

        with patch.object(w, "MAX_ATTEMPTS", 3), \
             patch.object(w.asyncio, "sleep", new=AsyncMock()) as sleep, \
             patch.object(w, "PostgreSQLPool") as pool:
            conn = AsyncMock()
            pool.acquire.return_value.__aenter__.return_value = conn
            await w._mark_failed("vid-1", attempts=1, message="boom")

        sleep.assert_awaited_once_with(30)  # first retry backoff
        # last execute call re-queues
        assert any("queued" in str(c.args[0]) for c in conn.execute.await_args_list)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_exhausted_attempts_marks_failed(self):
        from workers import video_worker as w

        with patch.object(w, "MAX_ATTEMPTS", 3), \
             patch.object(w, "PostgreSQLPool") as pool:
            conn = AsyncMock()
            pool.acquire.return_value.__aenter__.return_value = conn
            await w._mark_failed("vid-2", attempts=3, message="dead")

        sql = conn.execute.await_args_list[-1].args[0]
        assert "status = 'failed'" in sql

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_counts_attempt_and_handles_videoerror(self):
        from workers import video_worker as w

        with patch.object(w, "PostgreSQLPool") as pool, \
             patch.object(w, "produce_video", new=AsyncMock(side_effect=w.VideoError("nope"))), \
             patch.object(w, "_mark_failed", new=AsyncMock()) as failed:
            conn = AsyncMock()
            conn.fetchval = AsyncMock(return_value=1)
            pool.acquire.return_value.__aenter__.return_value = conn
            await w._process("vid-3")

        failed.assert_awaited_once()
        assert failed.await_args.args[1] == 1  # attempts passed through


# ===========================================================================
# API endpoints
# ===========================================================================


class TestVideoEndpoints:
    @pytest.mark.integration
    def test_all_endpoints_require_auth(self):
        assert client.post("/api/v1/videos/generate", json={"title": "x"}).status_code == 401
        assert client.get("/api/v1/videos").status_code == 401
        assert client.get(f"/api/v1/videos/{uuid4()}").status_code == 401
        assert client.delete(f"/api/v1/videos/{uuid4()}").status_code == 401

    @pytest.mark.integration
    def test_generate_rejects_bad_tone(self):
        from services import usage_service

        # usage dependency passes; invalid tone then fails body validation (422)
        with patch.object(usage_service, "get_user_plan", new=AsyncMock(return_value="pro")), \
             patch.object(usage_service, "get_monthly_usage", new=AsyncMock(return_value=0)):
            resp = client.post(
                "/api/v1/videos/generate",
                json={"title": "x", "tone": "dramatic"},
                headers=auth_header(),
            )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_generate_queues_video(self):
        from services import usage_service

        new_id = uuid4()
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=new_id)

        class Acq:
            async def __aenter__(self): return conn
            async def __aexit__(self, *a): return False

        with patch.object(usage_service, "get_user_plan", new=AsyncMock(return_value="pro")), \
             patch.object(usage_service, "get_monthly_usage", new=AsyncMock(return_value=0)), \
             patch("routers.videos.PostgreSQLPool.acquire", return_value=Acq()), \
             patch("routers.videos.record_usage", new=AsyncMock()):
            resp = client.post(
                "/api/v1/videos/generate",
                json={"title": "My Article", "tone": "casual", "voice": "male"},
                headers=auth_header(),
            )

        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        assert resp.json()["video_id"] == str(new_id)

    @pytest.mark.integration
    def test_generate_over_limit_blocked(self):
        from services import usage_service

        with patch.object(usage_service, "get_user_plan", new=AsyncMock(return_value="free")), \
             patch.object(usage_service, "get_monthly_usage", new=AsyncMock(return_value=5)):
            resp = client.post(
                "/api/v1/videos/generate",
                json={"title": "x"},
                headers=auth_header(),
            )
        assert resp.status_code == 403
        assert "Upgrade to Pro" in resp.json()["detail"]
