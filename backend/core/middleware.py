"""Middleware: request ID, structured logging, error handling."""
from __future__ import annotations

import uuid
from contextlib import suppress
from time import perf_counter

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to each request; propagate via response header."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request method, path, status, and duration."""

    def __init__(self, app: ASGIApp, logger):
        super().__init__(app)
        self._logger = logger

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = perf_counter()
        response = await call_next(request)
        duration = perf_counter() - start
        rid = getattr(request.state, "request_id", "-")
        self._logger.info(
            "%s %s %s %.3fs",
            request.method,
            request.url.path,
            response.status_code,
            duration,
            extra={"request_id": rid},
        )
        return response
