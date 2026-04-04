"""
Rate Limit Middleware — applies to /api/v1/third-party/ routes.
Adds X-RateLimit-* headers to every response.

Note: Actual rate limiting is done via the apply_rate_limit dependency
(which runs after auth). This middleware only adds response headers.
"""
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Adds rate limit response headers to third-party API responses.
    The actual rate limiting check is done by the apply_rate_limit dependency.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only add headers to third-party API routes (resource-based: /api/v1/payments, etc.)
        # Exclude admin, oauth, health, and webhook management endpoints
        if not (path.startswith("/api/v1/payments") or
                path.startswith("/api/v1/customers") or
                path.startswith("/api/v1/refunds") or
                path.startswith("/api/v1/events") or
                path.startswith("/api/v1/merchants") or
                path.startswith("/api/v1/third-party/webhooks")):
            return await call_next(request)

        response = await call_next(request)

        # Add rate limit headers if set by the dependency
        rate_result = getattr(request.state, "rate_limit_result", None)
        if rate_result:
            response.headers["X-RateLimit-Limit"] = str(rate_result.limit)
            response.headers["X-RateLimit-Remaining"] = str(rate_result.remaining)
            response.headers["X-RateLimit-Reset"] = str(rate_result.reset_at)
            response.headers["X-RateLimit-Window-Seconds"] = str(rate_result.window_seconds)

        return response
