"""Reject oversized request bodies before they are read (multipart is spooled to disk)."""

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings


class BodySizeLimitMiddleware:
    """Content-Length guard. Chunked bodies are still bounded by the proxy / file service."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            raw = dict(scope["headers"]).get(b"content-length")
            limit = get_settings().max_upload_bytes + 1024 * 1024  # multipart overhead
            if raw and raw.isdigit() and int(raw) > limit:
                body = b'{"error":{"code":"payload_too_large","message":"Requ\\u00eate trop volumineuse."}}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
