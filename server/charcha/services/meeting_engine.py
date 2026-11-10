"""Hold engines for occupied meetings or explicit, bounded host preparation."""
import asyncio
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from ..errors import ProviderError

RECONNECT_GRACE_SECONDS = 30
PRESENCE_CHECK_SECONDS = 5
MAX_PREPARATION_SECONDS = 900


@dataclass(frozen=True)
class Preparation:
    expires_at: float
    monotonic_deadline: float
    authorization_check: Callable[[], bool] | None = None

    def active(self, wall, monotonic):
        if wall >= self.expires_at or monotonic >= self.monotonic_deadline:
            return False
        try:
            return self.authorization_check is None or bool(self.authorization_check())
        except Exception:
            return False  # Revocation checks fail closed and cannot keep compute alive.


class MeetingEngineLifecycle:
    def __init__(self, store, transport, engine, *, resolve_engine=None, is_authorized=None):
        self.store, self.transport, self.engine = store, transport, engine
        self.resolve_engine = resolve_engine or (lambda code: self.engine)
        self.is_authorized = is_authorized or (lambda state: state.host_funded)
        self.last_connected: dict[str, float] = {}
        self.preparations: dict[str, Preparation] = {}
        # A removed/reconfigured room must release its previous engine's holds.
        # The provider registry, not this controller, owns client shutdown.
        self._known_engines = {id(engine): engine} if engine else {}
        if engine:
            engine.meeting_managed = True

    def _eligible(self, code, state, wall):
        if (state is None or not state.room.engine_on_demand
                or state.room.mode != "live" or state.expires_at <= wall):
            return None
        try:
            if not self.is_authorized(state):
                return None
            engine = self.resolve_engine(code)
        except Exception:
            return None
        if engine is None:
            return None
        # Real engines have settings; old local doubles use the Store defaults.
        settings = getattr(engine, "settings", self.store.settings)
        if not settings.evon_serverless:
            return None
        engine.meeting_managed = True
        self._known_engines[id(engine)] = engine
        return engine

    def prepare(self, code, *, account_deadline, seconds=MAX_PREPARATION_SECONDS,
                authorization_check=None):
        """Explicit authorized POST only; HTTP ownership/CSRF checks live upstream.

        Repeated button presses do not extend an active lease. The hold expires
        at the earliest of the account session, room, or 15-minute deadline.
        Engine readiness means a health response, not confirmed GPU allocation.
        """
        wall, monotonic = time.time(), time.monotonic()
        if (not isinstance(seconds, (int, float)) or isinstance(seconds, bool)
                or not math.isfinite(seconds) or seconds <= 0
                or seconds > MAX_PREPARATION_SECONDS
                or not isinstance(account_deadline, (int, float)) or isinstance(account_deadline, bool)
                or not math.isfinite(account_deadline) or account_deadline <= wall):
            raise ProviderError("The meeting preparation window is invalid or expired.", False)
        state = self.store.rooms.get(code)
        if self._eligible(code, state, wall) is None:
            raise ProviderError("Interpretation preparation is not available for this meeting.", False)
        existing = self.preparations.get(code)
        if existing is None or not existing.active(wall, monotonic):
            expiry = min(account_deadline, state.expires_at, wall + seconds)
            lease = Preparation(expiry, monotonic + expiry - wall, authorization_check)
            if not lease.active(wall, monotonic):
                raise ProviderError("Meeting preparation is no longer authorized.", False)
            self.preparations[code] = lease
        self.sync()
        return self.status(code)

    def cancel_preparation(self, code):
        """Remove prejoin authority only; occupied and other rooms retain holds."""
        self.preparations.pop(code, None)
        self.sync()
        return self.status(code)

    def status(self, code):
        """Read-only: no reconciliation, networking, keepalive or lease renewal."""
        wall, monotonic = time.time(), time.monotonic()
        try:
            engine = self.resolve_engine(code)
        except Exception:
            engine = None
        result = dict(engine.status()) if engine else {"state": "external"}
        lease = self.preparations.get(code)
        active = bool(lease and lease.active(wall, monotonic))
        result.update({
            "preparation_active": active,
            "preparation_expires_at": datetime.fromtimestamp(lease.expires_at, UTC).isoformat()
                if active else None,
            "preparation_remaining_seconds": max(0, math.ceil(min(
                lease.expires_at - wall, lease.monotonic_deadline - monotonic))) if active else 0,
            "preparation_max_seconds": MAX_PREPARATION_SECONDS,
        })
        return result

    def sync(self):
        grouped, connected, occupied = {}, {}, set()
        monotonic, wall = time.monotonic(), time.time()
        for code, state in list(self.store.rooms.items()):
            engine = self._eligible(code, state, wall)
            if engine is None:
                continue
            held = grouped.setdefault(id(engine), set())
            members = {p.id for p in state.room.participants
                       if not p.is_agent and not p.is_demo and self.store.is_active(code, p.id)}
            audio = self.transport.rooms.get(code)
            if not members or not audio or audio.closed or not audio.room:
                continue
            remote = audio.room.remote_participants
            live = (not audio.disconnected and not getattr(audio, "reconnecting", False)
                    and bool(members.intersection(remote)))
            last = monotonic if live else self.last_connected.get(code)
            if last is not None and (live or monotonic - last < RECONNECT_GRACE_SECONDS):
                connected[code] = last
                held.add(code)
                occupied.add(code)
        self.last_connected = connected
        # Connected media supersedes preparation. A leftover lease must not
        # keep compute running after a participant's explicit last departure.
        preparing = {}
        for code, lease in list(self.preparations.items()):
            engine = self._eligible(code, self.store.rooms.get(code), wall)
            if code in occupied or engine is None or not lease.active(wall, monotonic):
                self.preparations.pop(code, None)
                continue
            grouped.setdefault(id(engine), set()).add(code)
            preparing.setdefault(id(engine), set()).add(code)
        for key, engine in list(self._known_engines.items()):
            engine.preparing_rooms = preparing.get(key, set())
            engine.hold_meetings(grouped.get(key, set()))
            if key not in grouped and engine is not self.engine:
                self._known_engines.pop(key, None)

    async def run(self):
        while True:
            self.sync()
            await asyncio.sleep(PRESENCE_CHECK_SECONDS)
