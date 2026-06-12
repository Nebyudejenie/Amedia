"""Redis-backed sliding-window rate limiting middleware.

Limits (per minute):
  - Auth endpoints:   5 req/min per IP
  - Admin endpoints: 10 req/min per user
  - Write requests:  20 req/min per user
  - Read requests:  100 req/min per user

Falls back to in-memory counters if Redis is unavailable
(single-process only; fine for development).
"""
import time
import logging
from collections import defaultdict

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from auth.jwt_handler import decode_token_unsafe

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60

# (limit, scope) rules evaluated in order; first match wins
RULES = [
    {"prefix": "/auth/", "limit": 5, "by": "ip"},
    {"prefix": "/api/v1/admin/", "limit": 10, "by": "user"},
]
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
WRITE_LIMIT = 20
READ_LIMIT = 100

# Paths excluded from rate limiting
# /webhooks/telegram authenticates via its own secret token and may burst
EXEMPT_PATHS = {"/system/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/webhooks/telegram", "/webhooks/stripe"}

# In-memory fallback store: key -> list of timestamps
_memory_store: dict = defaultdict(list)


def _resolve_rule(request: Request) -> tuple[int, str]:
    """Return (limit, scope) for a request."""
    path = request.url.path
    for rule in RULES:
        if path.startswith(rule["prefix"]):
            return rule["limit"], rule["by"]
    if request.method in WRITE_METHODS:
        return WRITE_LIMIT, "user"
    return READ_LIMIT, "user"


def _identify(request: Request, by: str) -> str:
    """Build the rate-limit key subject: user id when available, else IP."""
    ip = request.client.host if request.client else "unknown"
    if by == "ip":
        return f"ip:{ip}"

    # Prefer user identity from bearer token (unverified decode is fine
    # for rate-limit keying; auth happens later in the request lifecycle)
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        payload = decode_token_unsafe(auth_header[7:])
        if payload and payload.get("sub"):
            return f"user:{payload['sub']}"
    return f"ip:{ip}"


async def _check_redis(key: str, limit: int) -> tuple[bool, int]:
    """Sliding window via Redis sorted set. Returns (allowed, retry_after)."""
    from clients import RedisClient

    redis = RedisClient._redis
    if redis is None:
        raise RuntimeError("Redis not initialized")

    now = time.time()
    window_start = now - WINDOW_SECONDS
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {f"{now}": now})
    pipe.zcard(key)
    pipe.expire(key, WINDOW_SECONDS + 5)
    results = await pipe.execute()
    count = results[2]

    if count > limit:
        oldest = await redis.zrange(key, 0, 0, withscores=True)
        retry_after = WINDOW_SECONDS
        if oldest:
            retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now))
        return False, retry_after
    return True, 0


def _check_memory(key: str, limit: int) -> tuple[bool, int]:
    """In-memory fallback (single process)."""
    now = time.time()
    window_start = now - WINDOW_SECONDS
    timestamps = [t for t in _memory_store[key] if t > window_start]
    timestamps.append(now)
    _memory_store[key] = timestamps

    if len(timestamps) > limit:
        retry_after = max(1, int(timestamps[0] + WINDOW_SECONDS - now))
        return False, retry_after
    return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-route rate limits before request processing."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        limit, by = _resolve_rule(request)
        subject = _identify(request, by)
        key = f"ratelimit:{subject}:{request.url.path if by == 'ip' else 'global'}"

        try:
            allowed, retry_after = await _check_redis(key, limit)
        except Exception:
            allowed, retry_after = _check_memory(key, limit)

        if not allowed:
            logger.warning(f"Rate limit exceeded: {subject} on {path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
