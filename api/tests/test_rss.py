"""Tests for RSS feed integration: parsing, dedup, backoff, endpoints."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app
from services.rss_fetcher import (
    FeedError,
    backoff_delay_minutes,
    fetch_feed,
    parse_feed_content,
    url_hash,
    validate_feed,
)
from auth.jwt_handler import create_access_token

client = TestClient(app)


def auth_header() -> dict:
    token = create_access_token(user_id=str(uuid4()), email="rss@example.com")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures: feed payloads
# ---------------------------------------------------------------------------

RSS2_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Tech News</title>
    <link>https://example.com</link>
    <item>
      <title>First Article</title>
      <link>https://example.com/a/1</link>
      <description>Summary of the first article</description>
      <author>jane@example.com</author>
      <category>tech</category>
      <category>ai</category>
      <pubDate>Wed, 10 Jun 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Second Article</title>
      <link>https://example.com/a/2</link>
      <description>Summary two</description>
    </item>
  </channel>
</rss>"""

ATOM_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Example</title>
  <entry>
    <title>Atom Post</title>
    <link href="https://example.org/posts/atom-1"/>
    <summary>Atom entry summary</summary>
    <updated>2026-06-10T12:00:00Z</updated>
    <author><name>Bob</name></author>
  </entry>
</feed>"""

NOT_A_FEED = b"<html><body><h1>Just a webpage</h1></body></html>"

# Broken XML but with a recoverable entry (feedparser bozo + entries)
PARTIALLY_BROKEN = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Broken & Co</title>
<item><title>Recoverable</title><link>https://example.com/ok</link></item>
"""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestFeedParsing:
    @pytest.mark.unit
    def test_parses_rss2(self):
        result = parse_feed_content(RSS2_FEED, "https://example.com/feed")
        assert result["title"] == "Example Tech News"
        assert len(result["entries"]) == 2

        first = result["entries"][0]
        assert first["title"] == "First Article"
        assert first["source_url"] == "https://example.com/a/1"
        assert first["description"] == "Summary of the first article"
        assert "tech" in first["categories"]
        assert first["published_at"] is not None
        assert first["published_at"].tzinfo is not None  # tz-aware

    @pytest.mark.unit
    def test_parses_atom(self):
        result = parse_feed_content(ATOM_FEED, "https://example.org/atom")
        assert result["title"] == "Atom Example"
        assert len(result["entries"]) == 1
        entry = result["entries"][0]
        assert entry["source_url"] == "https://example.org/posts/atom-1"
        assert entry["published_at"] is not None  # Atom <updated> used as fallback

    @pytest.mark.unit
    def test_rejects_html_page(self):
        with pytest.raises(FeedError):
            parse_feed_content(NOT_A_FEED, "https://example.com")

    @pytest.mark.unit
    def test_tolerates_partially_broken_xml(self):
        """bozo feeds with usable entries must still parse."""
        result = parse_feed_content(PARTIALLY_BROKEN, "https://example.com/feed")
        assert len(result["entries"]) == 1
        assert result["entries"][0]["source_url"] == "https://example.com/ok"

    @pytest.mark.unit
    def test_skips_entries_without_links(self):
        feed = b"""<rss version="2.0"><channel><title>T</title>
        <item><title>No link here</title></item>
        <item><title>Has link</title><link>https://e.com/x</link></item>
        </channel></rss>"""
        result = parse_feed_content(feed, "u")
        assert len(result["entries"]) == 1

    @pytest.mark.unit
    def test_handles_missing_dates(self):
        result = parse_feed_content(RSS2_FEED, "u")
        assert result["entries"][1]["published_at"] is None


# ---------------------------------------------------------------------------
# Fetching (network mocked)
# ---------------------------------------------------------------------------


class TestFeedFetching:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fetch_valid_feed(self):
        mock_response = httpx.Response(
            200, content=RSS2_FEED, request=httpx.Request("GET", "https://example.com/feed")
        )
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
            result = await fetch_feed("https://example.com/feed")
        assert result["title"] == "Example Tech News"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fetch_timeout_raises_feed_error(self):
        with patch(
            "httpx.AsyncClient.get",
            new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
        ):
            with pytest.raises(FeedError, match="Timed out"):
                await fetch_feed("https://slow.example.com/feed")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fetch_http_error_raises_feed_error(self):
        request = httpx.Request("GET", "https://example.com/feed")
        response = httpx.Response(404, request=request)
        with patch(
            "httpx.AsyncClient.get",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError("404", request=request, response=response)
            ),
        ):
            with pytest.raises(FeedError, match="HTTP 404"):
                await fetch_feed("https://example.com/feed")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_validate_feed_returns_metadata(self):
        mock_response = httpx.Response(
            200, content=ATOM_FEED, request=httpx.Request("GET", "https://example.org/atom")
        )
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
            info = await validate_feed("https://example.org/atom")
        assert info == {"title": "Atom Example", "entry_count": 1}


# ---------------------------------------------------------------------------
# Deduplication + backoff
# ---------------------------------------------------------------------------


class TestDeduplication:
    @pytest.mark.unit
    def test_url_hash_is_sha256_and_stable(self):
        h1 = url_hash("https://example.com/a/1")
        h2 = url_hash("https://example.com/a/1")
        h3 = url_hash("https://example.com/a/2")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64

    @pytest.mark.unit
    def test_url_hash_normalizes_whitespace(self):
        assert url_hash("  https://e.com/x  ") == url_hash("https://e.com/x")


class TestBackoff:
    @pytest.mark.unit
    def test_exponential_progression(self):
        base = 15
        assert backoff_delay_minutes(0, base) == 15
        assert backoff_delay_minutes(1, base) == 30
        assert backoff_delay_minutes(2, base) == 60
        assert backoff_delay_minutes(3, base) == 120
        assert backoff_delay_minutes(4, base) == 240

    @pytest.mark.unit
    def test_capped_at_24_hours(self):
        assert backoff_delay_minutes(20, 15) == 24 * 60


# ---------------------------------------------------------------------------
# Endpoints (auth + validation behavior; DB-backed paths covered in staging)
# ---------------------------------------------------------------------------


class TestFeedEndpoints:
    @pytest.mark.integration
    def test_endpoints_require_auth(self):
        assert client.get("/api/v1/feeds").status_code == 401
        assert client.post("/api/v1/feeds", json={"feed_url": "https://e.com/f"}).status_code == 401
        assert client.delete(f"/api/v1/feeds/{uuid4()}").status_code == 401
        assert client.get(f"/api/v1/feeds/{uuid4()}/articles").status_code == 401

    @pytest.mark.integration
    def test_create_rejects_malformed_url(self):
        resp = client.post(
            "/api/v1/feeds",
            json={"feed_url": "not-a-url"},
            headers=auth_header(),
        )
        assert resp.status_code == 422  # pydantic HttpUrl validation

    @pytest.mark.integration
    def test_create_rejects_bad_interval(self):
        resp = client.post(
            "/api/v1/feeds",
            json={"feed_url": "https://example.com/feed", "refresh_interval_minutes": 1},
            headers=auth_header(),
        )
        assert resp.status_code == 422  # below 5-minute minimum

    @pytest.mark.integration
    def test_update_with_no_fields_rejected(self, db_connection):
        resp = client.patch(
            f"/api/v1/feeds/{uuid4()}",
            json={},
            headers=auth_header(),
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_user_can_add_and_list_feed(self, db_connection, test_workspace, test_user):
        """Full add→list cycle with the network call mocked."""
        token = create_access_token(user_id=str(test_user), email="owner@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        mock_response = httpx.Response(
            200, content=RSS2_FEED, request=httpx.Request("GET", "https://example.com/itest-feed")
        )
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
            created = client.post(
                "/api/v1/feeds",
                json={"feed_url": f"https://example.com/itest-{uuid4()}"},
                headers=headers,
            )
        assert created.status_code == 201
        body = created.json()
        assert body["title"] == "Example Tech News"
        assert body["status"] == "active"

        listed = client.get("/api/v1/feeds", headers=headers)
        assert listed.status_code == 200
        assert "X-Total-Count" in listed.headers
