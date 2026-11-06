"""Bound requests before multipart parsing and keep voice references in memory."""
from starlette.formparsers import MultiPartParser
from starlette.responses import JSONResponse

from .services.voice import MAX_REFERENCE_BYTES

MAX_UPLOAD_BODY = MAX_REFERENCE_BYTES + 64 * 1024
# Starlette normally spills UploadFile after 1MiB. The body limiter below bounds
# the entire upload below this threshold, preventing reference clips touching disk.
MultiPartParser.spool_max_size = MAX_UPLOAD_BODY + 1


class RequestBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        path = scope.get("path")
        limit = (MAX_UPLOAD_BODY if path == "/api/voice-profiles" else
                 1_024_000 + 64 * 1024 if path == "/api/audio-lab/analyze" else 64 * 1024)
        headers = dict(scope.get("headers", []))
        try:
            too_large = int(headers.get(b"content-length", b"0")) > limit
        except ValueError:
            too_large = True
        if too_large:
            return await JSONResponse({"detail": "Request body exceeds the upload limit"}, 413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                # HTTPException propagates through FastAPI's body parser as a 413.
                from fastapi import HTTPException
                raise HTTPException(413, "Request body exceeds the upload limit")
            return message

        await self.app(scope, bounded_receive, send)
