"""Reject oversized request bodies before they are spooled (multipart is spooled to disk)."""

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings

_BODY = b'{"error":{"code":"payload_too_large","message":"Requ\\u00eate trop volumineuse."}}'


_DCE_UPLOAD = re.compile(r"^/bids/[^/]+/dce/?$")


class _TooLarge(Exception):
    pass


async def _send_413(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_BODY)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _BODY})


class BodySizeLimitMiddleware:
    """Bounds every request body: up front on ``Content-Length``, and while it is received
    (chunked bodies have no ``Content-Length``, so the stream itself is counted)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        s = get_settings()
        base = (
            s.max_dce_upload_bytes
            if _DCE_UPLOAD.match(scope.get("path", ""))
            else s.max_upload_bytes
        )
        limit = base + 1024 * 1024  # multipart overhead
        raw = dict(scope["headers"]).get(b"content-length")
        if raw and raw.isdigit() and int(raw) > limit:
            await _send_413(send)
            return

        received = 0
        exceeded = False
        started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _TooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if exceeded:  # the app turned the aborted read into its own error: answer 413
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _TooLarge:
            pass
        if exceeded and not started:
            await _send_413(send)
