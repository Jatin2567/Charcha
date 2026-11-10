"""Untrusted model response caps exercised entirely through local transports."""
import httpx
import pytest

from charcha.services.bounded_http import BoundedResponseTransport


class TrackedStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.reads = 0
        self.closes = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    async def aclose(self):
        self.closes += 1


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {"Content-Length":"9"}, {"Content-Length":"9999999999999999999999"},
    {"Content-Length":"-1"}, {"Content-Length":"8, 8"},
    {"Content-Encoding":"gzip"}, {"Content-Encoding":"br"},
    {"Content-Encoding":"deflate"}, {"Content-Encoding":"zstd"},
    {"Content-Encoding":"identity, gzip"},
])
async def test_bad_length_or_compression_is_rejected_without_reading_body(headers):
    stream = TrackedStream([b"private-response-body"])
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, headers=headers, stream=stream)
    transport = BoundedResponseTransport(8, httpx.MockTransport(respond))
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        with pytest.raises(httpx.RemoteProtocolError) as error:
            await client.get("https://model.example.com/v1/models",
                             headers={"Authorization":"Bearer private-key", "Accept-Encoding":"gzip, br"})
    assert requests[0].headers["Accept-Encoding"] == "identity"
    assert stream.reads == 0 and stream.closes == 1
    assert "private" not in str(error.value) and "model.example.com" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {"Content-Length":"1"}, {"Content-Encoding":"identity"}])
async def test_raw_chunk_count_stops_buffering_even_without_honest_length(headers):
    stream = TrackedStream([b"1234", b"56789", b"not-read"])
    transport = BoundedResponseTransport(8, httpx.MockTransport(
        lambda request: httpx.Response(200, headers=headers, stream=stream)))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.RemoteProtocolError):
            await client.get("https://model.example.com/v1/models")
    assert stream.reads == 2 and stream.closes == 1


@pytest.mark.asyncio
async def test_sse_stream_remains_incremental_and_closes_when_caller_stops():
    first, second = b'data: {"token":"hello"}\n\n', b'data: [DONE]\n\n'
    stream = TrackedStream([first, second])
    transport = BoundedResponseTransport(len(first) + len(second), httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"Content-Type":"text/event-stream"}, stream=stream)))
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        async with client.stream("POST", "https://model.example.com/v1/chat/completions") as response:
            assert stream.reads == 0  # Opening the stream never buffers the response.
            iterator = response.aiter_raw()
            assert await anext(iterator) == first
            assert stream.reads == 1  # The second network chunk was not pre-fetched.
        assert stream.closes == 1


@pytest.mark.asyncio
async def test_sse_limit_interrupts_after_prior_valid_chunk_without_releasing_overflow():
    stream = TrackedStream([b"first", b"too-large", b"ignored"])
    transport = BoundedResponseTransport(8, httpx.MockTransport(
        lambda request: httpx.Response(200, stream=stream)))
    async with httpx.AsyncClient(transport=transport) as client:
        async with client.stream("POST", "https://model.example.com/v1/chat/completions") as response:
            iterator = response.aiter_raw()
            assert await anext(iterator) == b"first"
            with pytest.raises(httpx.RemoteProtocolError):
                await anext(iterator)
    assert stream.reads == 2 and stream.closes == 1


@pytest.mark.asyncio
async def test_exact_limit_applies_per_response_and_does_not_change_payload():
    streams = []
    def respond(request):
        stream = TrackedStream([b"1234", b"5678"])
        streams.append(stream)
        return httpx.Response(200, headers={"Content-Length":"8", "Content-Encoding":"identity"}, stream=stream)
    async with httpx.AsyncClient(transport=BoundedResponseTransport(8, httpx.MockTransport(respond))) as client:
        for _ in range(2):
            assert (await client.get("https://model.example.com/v1/models")).content == b"12345678"
    assert all(stream.reads == 2 and stream.closes == 1 for stream in streams)


@pytest.mark.asyncio
async def test_redirect_is_not_followed_and_its_body_is_still_bounded():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(303, headers={"Location":"https://other.example.com", "Content-Length":"1000"},
                              stream=TrackedStream([b"not-consumed"]))
    async with httpx.AsyncClient(transport=BoundedResponseTransport(8, httpx.MockTransport(respond)),
                                follow_redirects=False) as client:
        with pytest.raises(httpx.RemoteProtocolError):
            await client.get("https://model.example.com/v1/models")
    assert len(requests) == 1 and requests[0].url.host == "model.example.com"


@pytest.mark.asyncio
async def test_preconsumed_transport_response_cannot_bypass_limit():
    transport = BoundedResponseTransport(8, httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"123456789")))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.RemoteProtocolError):
            await client.get("https://model.example.com/v1/models")


@pytest.mark.asyncio
async def test_closing_wrapper_closes_underlying_transport():
    class Inner(httpx.AsyncBaseTransport):
        closed = False
        async def aclose(self):
            self.closed = True
    inner = Inner()
    await BoundedResponseTransport(8, inner).aclose()
    assert inner.closed
