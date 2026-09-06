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


class ExplicitJSONCharsetMiddleware(BaseHTTPMiddleware):
    """Force `; charset=utf-8` onto JSON response Content-Type headers.

    FastAPI/Starlette's default JSONResponse sends `Content-Type:
    application/json` with no charset parameter. RFC 8259 says JSON is
    always UTF-8, but not every HTTP client assumes that when a charset
    is unspecified - Windows PowerShell 5.1's Invoke-RestMethod in
    particular falls back to ISO-8859-1/Windows-1252 in that case, which
    turns any UTF-8 multi-byte character (letters, degree/plus-minus
    signs, non-ASCII device-document content that flows through to a
    generated document plan, etc.) into mojibake (e.g. "Â°" instead of
    "°") purely on the client side - the actual stored/served bytes are
    correct UTF-8 the whole time. Being explicit here costs nothing and
    fixes that class of client for good, instead of asking every test
    script/client to work around it.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json") and "charset" not in content_type:
            response.headers["content-type"] = "application/json; charset=utf-8"
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
