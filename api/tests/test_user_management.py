"""Tests for user management, account flows, and admin endpoints."""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.auth import (
    hash_password,
    verify_password,
    validate_password_strength,
)
from api.auth.jwt_handler import create_access_token
from api.auth.security import clear_revocation_list

client = TestClient(app)

STRONG_PASSWORD = "SuperSecure123!@#"
WEAK_PASSWORDS = [
    "short1!A",                # too short
    "alllowercase123!!!!",     # no uppercase
    "NoNumbersHere!!!ABC",     # no number
    "NoSymbolsHere123ABC",     # no symbol
]


def make_token(user_id=None, email="user@example.com", is_admin=False) -> str:
    """Create a valid access token for tests."""
    return create_access_token(
        user_id=str(user_id or uuid4()),
        email=email,
        is_admin=is_admin,
    )


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Password utilities
# ============================================================================


class TestPasswordUtilities:
    @pytest.mark.unit
    def test_hash_and_verify_password(self):
        hashed = hash_password(STRONG_PASSWORD)
        assert hashed != STRONG_PASSWORD
        assert hashed.startswith("$2b$12$")  # bcrypt, cost 12
        assert verify_password(STRONG_PASSWORD, hashed) is True
        assert verify_password("WrongPassword1!", hashed) is False

    @pytest.mark.unit
    def test_hashes_are_salted(self):
        h1 = hash_password(STRONG_PASSWORD)
        h2 = hash_password(STRONG_PASSWORD)
        assert h1 != h2  # unique salt per hash

    @pytest.mark.unit
    def test_strong_password_accepted(self):
        assert validate_password_strength(STRONG_PASSWORD) is None

    @pytest.mark.unit
    @pytest.mark.parametrize("password", WEAK_PASSWORDS)
    def test_weak_passwords_rejected(self, password):
        assert validate_password_strength(password) is not None


# ============================================================================
# Profile endpoints
# ============================================================================


class TestProfileEndpoints:
    @pytest.mark.integration
    def test_get_me_requires_auth(self):
        resp = client.get("/api/v1/users/me")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_get_me_with_invalid_token(self):
        resp = client.get("/api/v1/users/me", headers=auth_header("not.a.token"))
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_patch_me_requires_auth(self):
        resp = client.patch("/api/v1/users/me", json={"full_name": "New Name"})
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_patch_me_empty_body_rejected(self):
        token = make_token()
        resp = client.patch("/api/v1/users/me", json={}, headers=auth_header(token))
        # 422 (no fields) or 404 (test user not in DB) — never 200
        assert resp.status_code in (404, 422)

    @pytest.mark.integration
    def test_patch_me_invalid_avatar_url(self):
        token = make_token()
        resp = client.patch(
            "/api/v1/users/me",
            json={"avatar_url": "not-a-url"},
            headers=auth_header(token),
        )
        assert resp.status_code == 422


# ============================================================================
# Admin endpoints
# ============================================================================


class TestAdminEndpoints:
    @pytest.mark.integration
    def test_admin_list_users_requires_auth(self):
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_admin_list_users_as_regular_user_forbidden(self):
        token = make_token(is_admin=False)
        resp = client.get("/api/v1/admin/users", headers=auth_header(token))
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin role required"

    @pytest.mark.integration
    def test_admin_list_users_as_admin(self, db_connection):
        token = make_token(is_admin=True)
        resp = client.get("/api/v1/admin/users", headers=auth_header(token))
        assert resp.status_code == 200
        assert "X-Total-Count" in resp.headers
        assert isinstance(resp.json(), list)

    @pytest.mark.integration
    def test_admin_list_pagination_limits(self):
        token = make_token(is_admin=True)
        # limit above maximum rejected by validation
        resp = client.get(
            "/api/v1/admin/users?limit=500", headers=auth_header(token)
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_admin_get_user_as_regular_user_forbidden(self):
        token = make_token(is_admin=False)
        resp = client.get(
            f"/api/v1/admin/users/{uuid4()}", headers=auth_header(token)
        )
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_admin_update_user_as_regular_user_forbidden(self):
        token = make_token(is_admin=False)
        resp = client.patch(
            f"/api/v1/admin/users/{uuid4()}",
            json={"is_active": False},
            headers=auth_header(token),
        )
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_admin_cannot_delete_self(self):
        admin_id = uuid4()
        token = make_token(user_id=admin_id, is_admin=True)
        resp = client.delete(
            f"/api/v1/admin/users/{admin_id}", headers=auth_header(token)
        )
        assert resp.status_code == 403
        assert "own account" in resp.json()["detail"]

    @pytest.mark.integration
    def test_admin_delete_nonexistent_user(self, db_connection):
        token = make_token(is_admin=True)
        resp = client.delete(
            f"/api/v1/admin/users/{uuid4()}", headers=auth_header(token)
        )
        assert resp.status_code == 404


# ============================================================================
# Account management flows
# ============================================================================


class TestPasswordFlows:
    @pytest.mark.integration
    def test_change_password_requires_auth(self):
        resp = client.post(
            "/auth/change-password",
            json={"current_password": "x", "new_password": STRONG_PASSWORD},
        )
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_change_password_weak_new_password(self):
        token = make_token()
        resp = client.post(
            "/auth/change-password",
            json={"current_password": STRONG_PASSWORD, "new_password": "weak"},
            headers=auth_header(token),
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_forgot_password_no_enumeration(self, db_connection):
        """Unknown emails must return the same 202 as known emails."""
        resp = client.post(
            "/auth/forgot-password",
            json={"email": f"nonexistent-{uuid4()}@example.com"},
        )
        assert resp.status_code == 202
        # Generic message, no hint about existence
        assert "if that email exists" in resp.json()["detail"].lower()

    @pytest.mark.integration
    def test_reset_password_invalid_token(self):
        resp = client.post(
            "/auth/reset-password",
            json={"reset_token": "garbage-token", "new_password": STRONG_PASSWORD},
        )
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_reset_password_weak_password_rejected_before_token_check(self):
        resp = client.post(
            "/auth/reset-password",
            json={"reset_token": "anything", "new_password": "weak"},
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reset_password_expired_token(self, db_connection, test_workspace, test_user):
        """An expired token in the DB must be rejected."""
        raw_token = "expired-test-token"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        await db_connection.execute(
            """
            INSERT INTO auth.password_reset_tokens (user_id, token_hash, expires_at)
            VALUES ($1, $2, $3)
            """,
            test_user,
            token_hash,
            datetime.now(timezone.utc) - timedelta(hours=1),
        )
        resp = client.post(
            "/auth/reset-password",
            json={"reset_token": raw_token, "new_password": STRONG_PASSWORD},
        )
        assert resp.status_code == 401


class TestEmailVerification:
    @pytest.mark.integration
    def test_verify_email_invalid_token(self):
        resp = client.post(
            "/auth/verify-email", json={"verification_token": "bad-token"}
        )
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_resend_verification_no_enumeration(self, db_connection):
        resp = client.post(
            "/auth/resend-verification",
            json={"email": f"ghost-{uuid4()}@example.com"},
        )
        assert resp.status_code == 202


# ============================================================================
# Login lockout
# ============================================================================


class TestLoginLockout:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_failed_logins_lock_account(self, db_connection, test_workspace):
        """After 5 failed logins the account locks for 15 minutes."""
        email = f"lockout-{uuid4()}@example.com"
        user_id = uuid4()
        await db_connection.execute(
            """
            INSERT INTO auth.users
                (id, workspace_id, email, name, role, password_hash, is_active)
            VALUES ($1, $2, $3, 'Lockout Test', 'editor', $4, true)
            """,
            user_id,
            test_workspace,
            email,
            hash_password(STRONG_PASSWORD),
        )

        # 5 failed attempts
        for _ in range(5):
            resp = client.post(
                "/auth/login",
                json={"email": email, "password": "WrongPassword1!"},
            )
            assert resp.status_code == 401

        # 6th attempt — even with the CORRECT password — is locked out
        resp = client.post(
            "/auth/login",
            json={"email": email, "password": STRONG_PASSWORD},
        )
        assert resp.status_code == 401
        assert "locked" in resp.json()["detail"].lower()
