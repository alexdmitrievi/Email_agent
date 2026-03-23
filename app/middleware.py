"""Middleware — request ID tracing, API rate limiting, CORS."""

import logging
import time
import uuid
from collections import defaultdict

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID into every request/response for tracing."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.monotonic()
        response = await call_next(request)
        elapsed = round((time.monotonic() - start) * 1000)

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s %s %dms",
            request.method, request.url.path, response.status_code, elapsed,
        )
        return response


class APIRateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter for API endpoints.

    Limits per IP: 60 requests/minute for webhooks, 30/minute for admin.
    """

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._limits = {
            "/webhooks/": 120,   # per minute
            "/admin/": 30,
            "/dashboard": 30,
            "/follow-ups": 10,
            "/daily-summary": 10,
        }
        self._default_limit = 200

    async def dispatch(self, request: Request, call_next):
        # Skip health and metrics
        path = request.url.path
        if path in ("/health", "/metrics"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{path}"
        now = time.monotonic()

        # Clean old entries (older than 60s)
        self._requests[key] = [t for t in self._requests[key] if now - t < 60]

        # Find matching limit
        limit = self._default_limit
        for prefix, lim in self._limits.items():
            if path.startswith(prefix):
                limit = lim
                break

        if len(self._requests[key]) >= limit:
            return Response(
                content='{"error": "rate_limit_exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        self._requests[key].append(now)
        return await call_next(request)
