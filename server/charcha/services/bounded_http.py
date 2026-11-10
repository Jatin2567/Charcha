"""Bound untrusted model responses before buffering or decoding them."""
from __future__ import annotations

import re

import httpx

MODEL_LIST_BYTES = 64 * 1024
TRANSLATION_BYTES = 512 * 1024


def response_limit_error() -> httpx.RemoteProtocolError:
    # Never include an endpoint, response body or authentication header.
    return httpx.RemoteProtocolError("Model response exceeded its allowed size or encoding.")


class LimitedResponseStream(httpx.AsyncByteStream):
    def __init__(self, inner: httpx.AsyncByteStream, max_bytes: int):
        self.inner, self.max_bytes = inner, max_bytes
        self.received = 0
        self.closed = False

    async def __aiter__(self):
        try:
            async for chunk in self.inner:
                self.received += len(chunk)
                if self.received > self.max_bytes:
                    raise response_limit_error()
                # Preserve streaming: do not aggregate or wait for later chunks.
                yield chunk
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self):
        if not self.closed:
            self.closed = True
            await self.inner.aclose()


class BoundedResponseTransport(httpx.AsyncBaseTransport):
    """Byte limit applies to every response, including errors, redirects and SSE."""
    def __init__(self, max_bytes: int, inner: httpx.AsyncBaseTransport | None = None):
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("A positive response limit is required")
        self.max_bytes = max_bytes
        self.inner = inner if inner is not None else httpx.AsyncHTTPTransport(trust_env=False, retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.headers["Accept-Encoding"] = "identity"
        response = await self.inner.handle_async_request(request)
        try:
            encoding = response.headers.get("Content-Encoding", "").strip().lower()
            length = response.headers.get("Content-Length")
            if encoding not in ("", "identity"):
                raise response_limit_error()
            if length is not None and (
                not re.fullmatch(r"[0-9]{1,20}", length.strip())
                or int(length.strip()) > self.max_bytes
            ):
                raise response_limit_error()
            # Alternate/mock transports may return an already consumed body.
            # The production AsyncHTTPTransport always supplies a raw stream.
            if response.is_stream_consumed and len(response.content) > self.max_bytes:
                raise response_limit_error()
            response.stream = LimitedResponseStream(response.stream, self.max_bytes)
            return response
        except BaseException:
            await response.aclose()
            raise

    async def aclose(self):
        await self.inner.aclose()


def bounded_model_client(max_bytes: int, *, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=BoundedResponseTransport(max_bytes),
        follow_redirects=False, trust_env=False, timeout=timeout,
        headers={"Accept-Encoding":"identity"})
