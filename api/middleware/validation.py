"""Input validation and sanitization utilities.

SQL injection is prevented by parameterized queries (asyncpg $1, $2 ...)
throughout the codebase. These helpers add XSS sanitization, format
validation, and length enforcement at the API boundary.
"""
import re
import html
from typing import Optional
from urllib.parse import urlparse

# Maximum field lengths
MAX_LENGTHS = {
    "title": 200,
    "name": 255,
    "email": 255,
    "url": 2000,
    "description": 5000,
    "content": 50000,
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Private/internal network ranges blocked for user-supplied URLs (SSRF guard)
_BLOCKED_HOSTS = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|169\.254\.|\[::1\])",
    re.IGNORECASE,
)


def sanitize_string(value: str, max_length: Optional[int] = None) -> str:
    """Strip HTML tags, escape entities, and trim to max length."""
    if not isinstance(value, str):
        return value
    cleaned = _HTML_TAG_RE.sub("", value)
    cleaned = html.escape(cleaned, quote=False).strip()
    if max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def validate_email_format(email: str) -> bool:
    """Check email matches a sane format and length."""
    return bool(email) and len(email) <= MAX_LENGTHS["email"] and bool(_EMAIL_RE.match(email))


def validate_url(url: str, allow_internal: bool = False) -> Optional[str]:
    """Validate a user-supplied URL; returns error message or None.

    Blocks non-http(s) schemes and internal network targets (SSRF guard).
    Webhook URLs and content source URLs must pass this check.
    """
    if not url or len(url) > MAX_LENGTHS["url"]:
        return "URL is missing or too long"

    try:
        parsed = urlparse(url)
    except Exception:
        return "URL is malformed"

    if parsed.scheme not in ("http", "https"):
        return "URL must use http or https"

    if not parsed.hostname:
        return "URL must include a hostname"

    if not allow_internal and _BLOCKED_HOSTS.match(parsed.hostname):
        return "URL must not target internal networks"

    return None


def enforce_length(field_name: str, value: str) -> Optional[str]:
    """Check a field against its configured max length; returns error or None."""
    limit = MAX_LENGTHS.get(field_name)
    if limit and value and len(value) > limit:
        return f"{field_name} must be at most {limit} characters"
    return None


def redact_sensitive(data: dict) -> dict:
    """Redact passwords/tokens/keys from dicts before logging."""
    SENSITIVE = {"password", "token", "secret", "key", "authorization",
                 "access_token", "refresh_token", "password_hash", "api_key"}
    redacted = {}
    for k, v in data.items():
        if any(s in k.lower() for s in SENSITIVE):
            redacted[k] = "***REDACTED***"
        elif isinstance(v, dict):
            redacted[k] = redact_sensitive(v)
        else:
            redacted[k] = v
    return redacted
