"""
Request ID Middleware — attaches a unique ID to every request/response.
"""
from uuid import uuid4
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Generates a unique request ID for tracing and debugging.
    If client sends X-Request-ID, it's preserved. Otherwise, one is generated.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", f"req_{uuid4().hex[:12]}")
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response
