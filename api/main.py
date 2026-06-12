"""Arada Intelligence OS — FastAPI backend."""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest

from clients import PostgreSQLPool, RedisClient, MinIOClient, QdrantClient
from config import settings
from routers import auth, account, users, content, health, media, workflow, ml, webhooks, analytics, feeds, telegram
from middleware.rate_limit import RateLimitMiddleware
from middleware.security_headers import SecurityHeadersMiddleware, SafeErrorMiddleware

logger = logging.getLogger(__name__)

# Metrics
request_count = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
request_duration = Histogram(
    "http_request_duration_seconds", "HTTP request duration", ["method", "endpoint"]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: init + cleanup on startup/shutdown."""
    # Startup
    logger.info("Arada API starting up")
    await PostgreSQLPool.init()
    await RedisClient.init()
    MinIOClient.init()
    await QdrantClient.init()
    yield
    # Shutdown
    logger.info("Arada API shutting down")
    await PostgreSQLPool.close()
    await RedisClient.close()
    await QdrantClient.close()


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# Security middleware (order matters: outermost added last)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SafeErrorMiddleware)

# CORS — restricted origins, methods, and headers for credentialed requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
    max_age=3600,
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all requests for tracing."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record request metrics."""
    with request_duration.labels(
        method=request.method, endpoint=request.url.path
    ).time():
        response = await call_next(request)
    request_count.labels(
        method=request.method, endpoint=request.url.path, status=response.status_code
    ).inc()
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "request_id": getattr(request.state, "request_id", "unknown")},
    )


# Routes
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(users.router)
app.include_router(feeds.router)
app.include_router(telegram.router)
app.include_router(content.router)
app.include_router(workflow.router)
app.include_router(media.router)
app.include_router(health.router)
app.include_router(ml.router)
app.include_router(webhooks.router)
app.include_router(analytics.router)

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return generate_latest()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info",
    )
