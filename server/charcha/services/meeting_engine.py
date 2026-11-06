"""Keep the shared GPU warm only while authorized meetings have connected members."""
import asyncio
import time

RECONNECT_GRACE_SECONDS = 30
PRESENCE_CHECK_SECONDS = 5


class MeetingEngineLifecycle:
    def __init__(self, store, transport, engine):
        self.store, self.transport, self.engine = store, transport, engine
        self.last_connected: dict[str, float] = {}
        if engine:
            engine.meeting_managed = True

    def sync(self):
        if not self.engine or not self.store.settings.evon_serverless:
            return
        held, connected = set(), {}
        monotonic, wall = time.monotonic(), time.time()
        for code, state in list(self.store.rooms.items()):
            if (not state.host_funded or not state.room.engine_on_demand
                    or state.room.mode != "live" or state.expires_at <= wall):
                continue
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
        self.last_connected = connected
        self.engine.hold_meetings(held)

    async def run(self):
        while True:
            self.sync()
            await asyncio.sleep(PRESENCE_CHECK_SECONDS)
