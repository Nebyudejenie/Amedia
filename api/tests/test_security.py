"""Tests for security middleware: headers, rate limiting, validation, API keys."""
import pytest
from fastapi.testclient import TestClient

from main import app
from middleware.validation import (
    sanitize_string,
    validate_email_format,
    validate_url,
    enforce_length,
    redact_sensitive,
)
from middleware.rate_limit import _resolve_rule, _check_memory, _memory_store

client = TestClient(app)


# ============================================================================
# Security headers
# ============================================================================


class TestSecurityHeaders:
    @pytest.mark.integration
    def test_all_security_headers_present(self):
        resp = client.get("/system/health")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-XSS-Protection"] == "1; mode=block"
        assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]
        assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.integration
    def test_request_id_header_present(self):
        resp = client.get("/system/health")
        assert "X-Request-ID" in resp.headers

    @pytest.mark.integration
    def test_errors_do_not_leak_internals(self):
        """Generic 500 with request_id; no stack traces or paths."""
        resp = client.get("/nonexistent-endpoint-xyz")
        assert resp.status_code == 404
        body = resp.json()
        assert "Traceback" not in str(body)
        assert "/home/" not in str(body)


# ============================================================================
# Rate limiting
# ============================================================================


class TestRateLimiting:
    def setup_method(self):
        _memory_store.clear()

    @pytest.mark.unit
    def test_auth_endpoints_get_strictest_limit(self):
        class FakeRequest:
            method = "POST"

            class url:
                path = "/auth/login"

        limit, by = _resolve_rule(FakeRequest)
        assert limit == 5
        assert by == "ip"

    @pytest.mark.unit
    def test_admin_endpoints_limit(self):
        class FakeRequest:
            method = "GET"

            class url:
                path = "/api/v1/admin/users"

        limit, by = _resolve_rule(FakeRequest)
        assert limit == 10
        assert by == "user"

    @pytest.mark.unit
    def test_write_vs_read_limits(self):
        class WriteReq:
            method = "POST"

            class url:
                path = "/content/sources"

        class ReadReq:
            method = "GET"

            class url:
                path = "/content/sources"

        assert _resolve_rule(WriteReq)[0] == 20
        assert _resolve_rule(ReadReq)[0] == 100

    @pytest.mark.unit
    def test_memory_window_blocks_after_limit(self):
        key = "test:subject"
        for _ in range(5):
            allowed, _ = _check_memory(key, 5)
            assert allowed is True
        allowed, retry_after = _check_memory(key, 5)
        assert allowed is False
        assert retry_after >= 1

    @pytest.mark.integration
    def test_login_rate_limited_after_burst(self):
        """6th rapid login attempt from same IP returns 429 with Retry-After."""
        _memory_store.clear()
        last = None
        for _ in range(8):
            last = client.post(
                "/auth/login",
                json={"email": "rl-test@example.com", "password": "WrongPass1!xx"},
            )
            if last.status_code == 429:
                break
        assert last.status_code == 429
        assert "Retry-After" in last.headers

    @pytest.mark.integration
    def test_health_endpoint_exempt_from_rate_limit(self):
        for _ in range(20):
            resp = client.get("/system/health")
            assert resp.status_code != 429


# ============================================================================
# Input validation
# ============================================================================


class TestInputValidation:
    @pytest.mark.unit
    def test_sanitize_strips_html(self):
        dirty = '<script>alert("xss")</script>Hello <b>World</b>'
        clean = sanitize_string(dirty)
        assert "<script>" not in clean
        assert "<b>" not in clean
        assert "Hello" in clean

    @pytest.mark.unit
    def test_sanitize_enforces_max_length(self):
        assert len(sanitize_string("a" * 500, max_length=200)) == 200

    @pytest.mark.unit
    def test_email_format_validation(self):
        assert validate_email_format("user@example.com") is True
        assert validate_email_format("not-an-email") is False
        assert validate_email_format("") is False
        assert validate_email_format("a@b") is False

    @pytest.mark.unit
    def test_url_validation_blocks_internal_targets(self):
        """SSRF guard: webhook URLs must not target internal networks."""
        assert validate_url("https://example.com/webhook") is None
        assert validate_url("http://localhost:8000/admin") is not None
        assert validate_url("http://127.0.0.1/") is not None
        assert validate_url("http://10.0.0.5/internal") is not None
        assert validate_url("http://192.168.1.200:8000/") is not None
        assert validate_url("ftp://example.com/file") is not None
        assert validate_url("javascript:alert(1)") is not None

    @pytest.mark.unit
    def test_length_enforcement(self):
        assert enforce_length("title", "x" * 200) is None
        assert enforce_length("title", "x" * 201) is not None
        assert enforce_length("description", "x" * 5001) is not None

    @pytest.mark.unit
    def test_sensitive_data_redacted_for_logging(self):
        data = {
            "email": "user@example.com",
            "password": "secret123",
            "access_token": "eyJhbGc...",
            "nested": {"api_key": "ak_12345", "name": "ok"},
        }
        redacted = redact_sensitive(data)
        assert redacted["email"] == "user@example.com"
        assert redacted["password"] == "***REDACTED***"
        assert redacted["access_token"] == "***REDACTED***"
        assert redacted["nested"]["api_key"] == "***REDACTED***"
        assert redacted["nested"]["name"] == "ok"


# ============================================================================
# Service API keys
# ============================================================================


class TestServiceAPIKeys:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_and_verify_key(self, db_connection):
        from auth.api_keys import create_service_key, verify_service_key

        created = await create_service_key("ml-worker", ["ml:predict"])
        assert created["api_key"].startswith("ak_")
        assert created["scopes"] == ["ml:predict"]

        identity = await verify_service_key(created["api_key"])
        assert identity["service_name"] == "ml-worker"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_verify_rejects_garbage_key(self, db_connection):
        from fastapi import HTTPException
        from auth.api_keys import verify_service_key

        with pytest.raises(HTTPException) as exc:
            await verify_service_key("ak_definitely-not-real")
        assert exc.value.status_code == 401

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_scope_enforcement(self, db_connection):
        from fastapi import HTTPException
        from auth.api_keys import create_service_key, verify_service_key

        created = await create_service_key("webhook-worker", ["webhooks:deliver"])
        with pytest.raises(HTTPException) as exc:
            await verify_service_key(created["api_key"], required_scope="ml:predict")
        assert exc.value.status_code == 403

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_revoked_key_rejected(self, db_connection):
        from uuid import UUID
        from fastapi import HTTPException
        from auth.api_keys import (
            create_service_key,
            verify_service_key,
            revoke_service_key,
        )

        created = await create_service_key("temp-service", [])
        await revoke_service_key(UUID(created["id"]))
        with pytest.raises(HTTPException) as exc:
            await verify_service_key(created["api_key"])
        assert exc.value.status_code == 401
