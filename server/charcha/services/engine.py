"""Meeting-held model readiness. Status reads never contact the GPU."""
import asyncio
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from ..errors import ProviderError

MEETING_KEEPALIVE_SECONDS = 45


class InterpretationEngine:
    def __init__(self, settings, headers, *, client=None):
        self.settings = settings
        self.headers = headers
        self.task = None
        self.state = "idle" if settings.evon_serverless else "external"
        self.ready_until = 0.0
        self.started = None
        self.duration_ms = None
        self.observed_at = None
        self.meeting_managed = False
        self.meeting_rooms: set[str] = set()
        # A bounded host-requested prejoin hold is distinct from an occupied call.
        self.preparing_rooms: set[str] = set()
        self.meeting_task = None
        self.client = client if client is not None else httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=165)

    def status(self):
        state = self.state
        if state == "ready" and time.monotonic() > self.ready_until:
            state = "idle"
        return {"state": state, "startup_ms": self.duration_ms, "observed_at": self.observed_at,
                "elapsed_ms": round((time.monotonic()-self.started)*1000) if state == "starting" else None,
                "lifecycle": "meeting" if self.meeting_managed else "request",
                "active_meetings": len(self.meeting_rooms - self.preparing_rooms),
                "preparing_meetings": len(self.meeting_rooms & self.preparing_rooms)}

    def hold_meetings(self, codes: set[str]):
        """Called by media/session or bounded prejoin reconciliation, never a status GET."""
        self.meeting_rooms = set(codes)
        if not self.settings.evon_serverless:
            return
        if codes:
            if self.meeting_task is None or self.meeting_task.done():
                self.meeting_task = asyncio.create_task(self._keep_meetings_warm())
                self.meeting_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        else:
            if self.meeting_task and not self.meeting_task.done():
                self.meeting_task.cancel()
            if self.task and not self.task.done():
                self.task.cancel()

    async def _keep_meetings_warm(self):
        while self.meeting_rooms:
            try:
                await self.ensure_ready(refresh=True)
            except ProviderError:
                # Show the failure and retry at a bounded cadence while occupied.
                pass
            await asyncio.sleep(MEETING_KEEPALIVE_SECONDS)

    def touch(self):
        if self.settings.evon_serverless:
            self.state = "ready"
            self.ready_until = time.monotonic() + 90

    def begin(self, *, refresh=False):
        if not self.settings.evon_serverless:
            return
        if self.meeting_managed and not self.meeting_rooms:
            raise ProviderError("Prepare the meeting or connect to an active meeting before starting interpretation.", False)
        if self.task and not self.task.done():
            return
        warm_check = self.status()["state"] == "ready"
        if warm_check and not refresh:
            return
        if not warm_check:
            self.state = "starting"
            self.started = time.monotonic()
        self.task = asyncio.create_task(self._start(warm_check=warm_check))
        # Surface failure through status/ensure_ready, without an unhandled task error.
        self.task.add_done_callback(lambda task: None if task.cancelled() else task.exception())

    async def ensure_ready(self, *, refresh=False):
        if not self.settings.evon_serverless:
            return
        self.begin(refresh=refresh)
        if self.task:
            await asyncio.shield(self.task)

    async def _start(self, *, warm_check=False):
        if not warm_check:
            self.state = "starting"
            self.started = time.monotonic()
            self.duration_ms = None
        base = self.settings.evon_base_url.rstrip("/").removesuffix("/v1")
        origin = urlsplit(base)
        url = base + "/health"
        try:
            if origin.scheme != "https" or not (origin.hostname or "").endswith(".modal.run"):
                raise ValueError("Invalid model destination")
            async with asyncio.timeout(900):
                for _ in range(7):
                    response = await self.client.get(url, headers=self.headers())
                    if response.status_code == 200:
                        if not warm_check:
                            self.duration_ms = round((time.monotonic()-self.started)*1000, 2)
                        self.observed_at = datetime.now(UTC).isoformat()
                        self.touch()
                        return
                    if response.status_code != 303:
                        raise ValueError("Model startup failed")
                    next_url = urljoin(url, response.headers.get("location", ""))
                    parsed = urlsplit(next_url)
                    if (parsed.scheme, parsed.netloc, parsed.path) != (origin.scheme, origin.netloc, "/health"):
                        raise ValueError("Invalid startup continuation")
                    url = next_url
            raise ValueError("Model startup exhausted its continuations")
        except asyncio.CancelledError:
            self.state = "idle"
            raise
        except Exception:
            self.state = "unavailable"
            self.observed_at = datetime.now(UTC).isoformat()
            raise ProviderError("Interpretation could not start. Check model availability and retry when ready.", False) from None

    async def aclose(self):
        self.meeting_rooms.clear()
        self.preparing_rooms.clear()
        if self.meeting_task and not self.meeting_task.done():
            self.meeting_task.cancel()
            await asyncio.gather(self.meeting_task, return_exceptions=True)
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        await self.client.aclose()
