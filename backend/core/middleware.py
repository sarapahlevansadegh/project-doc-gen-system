"""Middleware: request ID, structured logging, error handling."""
from __future__ import annotations

import uuid
from time import perf_counter

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestIDMiddleware:
    """Attach a unique request ID to each request; propagate via response header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())[:8]
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", request_id)
            await send(message)

        await self.app(scope, receive, send_wrapper)


class ExplicitJSONCharsetMiddleware:
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

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                content_type = headers.get("content-type", "")
                if content_type.startswith("application/json") and "charset" not in content_type:
                    headers["content-type"] = "application/json; charset=utf-8"
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RequestLoggingMiddleware:
    """Log request method, path, status, and duration."""

    def __init__(self, app: ASGIApp, logger) -> None:
        self.app = app
        self._logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = perf_counter()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration = perf_counter() - start
        rid = scope.get("state", {}).get("request_id", "-")
        self._logger.info(
            "%s %s %s %.3fs",
            scope["method"],
            scope["path"],
            status_code,
            duration,
            extra={"request_id": rid},
        )