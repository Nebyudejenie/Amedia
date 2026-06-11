"""Security headers + safe error handling middleware."""
import logging
import uuid

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach OWASP-recommended security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


class SafeErrorMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions; never leak internals to the client.

    Full traceback is logged server-side with a request_id; the client
    receives only a generic message + that request_id for support.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        request.state.request_id = request_id

        try:
            return await call_next(request)
        except Exception:
            # Log full details server-side only
            logger.exception(
                f"Unhandled error request_id={request_id} "
                f"method={request.method} path={request.url.path}"
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
            )
