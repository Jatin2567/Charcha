"""Automatic, conservative timing evidence; no raw audio or transcript persistence.

The source boundary is an energy-derived end on server ingress, not a human
annotation or the microphone's clock. Receiver observations are client claims
mapped to the server clock with an explicit uncertainty bound. Neither proves
physical sound left a speaker.
"""
from __future__ import annotations

import array
import math
import secrets
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..auth import bearer_token
from ..models import now

TOPIC = "charcha.latency.v1"
BOUNDARY = "server_ingress_energy_end"
MEASUREMENT = "server_ingress_energy_end_to_browser_decoded_onset_estimate"
CLOCK_TTL_MS = 60000
MARKER_TTL_MS = 120000


def clock_ms():
    return time.monotonic() * 1000


class SourceEndTracker:
    """Association is unavailable when finals and energy segments are ambiguous.

    A quiet interval must actually have been received. Wall-clock silence after
    a lost track is not counted as speech ending. Noise can trigger energy, so
    all successful associations remain explicitly estimates.
    """
    def __init__(self):
        self.last_frame = None
        self.last_energy = None
        self.voiced_frames = 0
        self.active = False
        self.ends = deque(maxlen=8)
        self.reason = "no_source_boundary"

    def reset(self, reason="source_discontinuity"):
        self.last_frame = self.last_energy = None
        self.voiced_frames = 0
        self.active = False
        self.ends.clear()
        self.reason = reason

    def feed(self, pcm: bytes, at_ms=None):
        at_ms = clock_ms() if at_ms is None else at_ms
        if self.last_frame is not None and at_ms - self.last_frame > 500:
            self.reset()
        self.last_frame = at_ms
        values = array.array("h")
        values.frombytes(pcm[:len(pcm) - len(pcm) % 2])
        if sys.byteorder != "little":
            values.byteswap()
        if not values:
            return
        rms = math.sqrt(sum(v * v for v in values) / len(values)) / 32768
        if rms >= (.004 if self.active else .008):
            self.voiced_frames += 1
            self.last_energy = at_ms
            if self.voiced_frames >= 3:
                self.active = True
        elif self.active and self.last_energy is not None and at_ms - self.last_energy >= 200:
            self.ends.append(self.last_energy)
            self.active = False
            self.voiced_frames = 0
        elif not self.active:
            self.voiced_frames = 0

    def take(self, at_ms=None):
        at_ms = clock_ms() if at_ms is None else at_ms
        eligible = [value for value in self.ends if 0 <= at_ms - value <= 30000]
        self.ends.clear()
        status = ("energy_estimate" if len(eligible) == 1 and not self.active
                  else "ambiguous_source_boundary" if eligible or self.active else self.reason)
        end = eligible[0] if status == "energy_estimate" else None
        return {"source_end_server_ms": end, "source_boundary": BOUNDARY,
                "source_end_status": status, "transcript_server_ms": at_ms,
                "source_end_to_transcript_ms": round(at_ms - end, 2) if end is not None else None}


class LatencyObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    marker_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    status: Literal["detected", "ambiguous", "muted", "blocked", "timeout"]
    observed_server_ms: float | None = Field(default=None, ge=0)
    clock_id: str | None = Field(default=None, min_length=16, max_length=64)
    clock_rtt_ms: float | None = Field(default=None, ge=0, le=1000)
    clock_age_ms: float | None = Field(default=None, ge=0, le=CLOCK_TTL_MS)
    poll_interval_ms: float = Field(ge=10, le=500)

    @model_validator(mode="after")
    def detection_needs_clock(self):
        if self.status == "detected" and any(v is None for v in (
                self.observed_server_ms, self.clock_id, self.clock_rtt_ms, self.clock_age_ms)):
            raise ValueError("A detection requires a recent clock observation")
        if self.status != "detected" and self.observed_server_ms is not None:
            raise ValueError("Unmeasured observations cannot contain a playback timestamp")
        return self


@dataclass
class Marker:
    code: str
    public: dict
    listeners: set[str]
    expires_ms: float
    first_pcm_ms: float | None = None


class TurnLatency:
    def __init__(self, store):
        self.store = store
        self.markers: dict[str, Marker] = {}
        self.clocks: dict[str, tuple[str, str, float]] = {}
        self.samples: dict[str, deque] = {}

    def _append(self, marker, listener_id, status, **values):
        public = marker.public
        source_end = public.get("source_end_server_ms")
        value = {"marker_id": public["marker_id"], "utterance_id": public["utterance_id"],
                 "listener_id": listener_id, "source_language": public["source_language"],
                 "target_language": public["target_language"], "status": status,
                 "measurement": MEASUREMENT, "source_boundary": BOUNDARY,
                 "source_end_status": public["source_end_status"],
                 "latency_ms": None, "uncertainty_ms": None,
                 "source_end_to_first_pcm_ms": round(marker.first_pcm_ms - source_end, 2)
                    if marker.first_pcm_ms is not None and source_end is not None else None,
                 "physical_playback_measured": False, "client_reported": True,
                 "created_at": now().isoformat(), **values}
        self.samples.setdefault(marker.code, deque(maxlen=500)).append(value)
        while len(self.samples) > 200:
            self.samples.pop(next(iter(self.samples)))
        return value

    def prune(self):
        current = clock_ms()
        for marker_id, marker in list(self.markers.items()):
            if marker.expires_ms < current:
                for listener in marker.listeners:
                    self._append(marker, listener, "unreported")
                self.markers.pop(marker_id, None)
        for key, (_, _, stamp) in list(self.clocks.items()):
            if current - stamp > CLOCK_TTL_MS:
                self.clocks.pop(key, None)

    def clock(self, code, listener):
        self.prune()
        # A fresh calibration replaces this listener's older probes only beyond
        # a small bounded set, allowing in-flight reports from a previous probe.
        own = [key for key, (room, pid, _) in self.clocks.items() if (room, pid) == (code, listener)]
        for key in own[:-7]:
            self.clocks.pop(key, None)
        stamp, key = clock_ms(), secrets.token_urlsafe(18)
        self.clocks[key] = (code, listener, stamp)
        return {"clock_id": key, "server_ms": stamp, "expires_in_ms": CLOCK_TTL_MS}

    def issue(self, state, speaker, language, context):
        self.prune()
        listeners = {p.id for p in state.room.participants if p.id != speaker and p.language == language
                     and not p.is_agent and not p.is_demo and self.store.is_active(state.room.code, p.id)}
        if not listeners or len(self.markers) >= 1000:
            return None
        stamp, marker_id = clock_ms(), secrets.token_urlsafe(18)
        source_end = context.get("source_end_server_ms")
        if not isinstance(source_end, (float, int)) or not math.isfinite(source_end) or not 0 <= stamp - source_end <= MARKER_TTL_MS:
            source_end = None
        public = {"marker_id": marker_id, "utterance_id": context["utterance_id"],
                  "speaker_id": speaker, "source_language": context["source_language"],
                  "target_language": language, "track_name": f"translated:{speaker}:{language}",
                  "source_end_server_ms": source_end, "source_boundary": BOUNDARY,
                  "source_end_status": context.get("source_end_status", "no_source_boundary"),
                  "published_server_ms": stamp, "expires_in_ms": MARKER_TTL_MS}
        self.markers[marker_id] = Marker(state.room.code, public, listeners, stamp + MARKER_TTL_MS)
        return public

    def first_pcm(self, marker_id):
        if marker := self.markers.get(marker_id):
            marker.first_pcm_ms = clock_ms()

    def finalize_room(self, code):
        """Close unanswered observations explicitly before saving a final report."""
        for marker_id, marker in list(self.markers.items()):
            if marker.code == code:
                for listener in marker.listeners:
                    self._append(marker, listener, "unreported", reason="meeting_ended_before_report")
                self.markers.pop(marker_id, None)
        for key, (room, _, _) in list(self.clocks.items()):
            if room == code:
                self.clocks.pop(key, None)

    def report(self, code, listener=None):
        # Retain bounded samples after room removal so expiry can save a final
        # snapshot; prune only pending marker/clock expirations.
        self.prune()
        rows = list(self.samples.get(code, ()))
        if listener is not None:
            rows = [r for r in rows if r["listener_id"] == listener]
        return {"measurement": MEASUREMENT, "physical_playback_measured": False, "samples": rows}

    def observe(self, code, listener, body: LatencyObservation):
        self.prune()
        marker = self.markers.get(body.marker_id)
        if not marker or marker.code != code or listener not in marker.listeners:
            raise HTTPException(404, "This playback observation is unavailable")
        state = self.store.room(code)
        member = next((p for p in state.room.participants if p.id == listener), None)
        if not member or member.language != marker.public["target_language"]:
            raise HTTPException(409, "Listening language changed before this observation")
        values = {}
        status = body.status
        if status == "detected":
            calibration = self.clocks.get(body.clock_id)
            current = clock_ms()
            if not calibration or calibration[:2] != (code, listener):
                raise HTTPException(422, "A fresh clock observation for this membership is required")
            uncertainty = body.clock_rtt_ms / 2 + body.poll_interval_ms + 20
            if (current - calibration[2] > CLOCK_TTL_MS
                    or body.observed_server_ms > current + uncertainty
                    or body.observed_server_ms < marker.public["published_server_ms"] - uncertainty
                    or body.observed_server_ms - marker.public["published_server_ms"] > MARKER_TTL_MS):
                raise HTTPException(422, "Playback observation is outside its timing window")
            source_end = marker.public["source_end_server_ms"]
            if marker.first_pcm_ms is None:
                status = "ambiguous"
            elif source_end is None:
                status = "source_unavailable"
            elif body.observed_server_ms < marker.first_pcm_ms - uncertainty or body.observed_server_ms < source_end:
                status = "ambiguous"
            else:
                values = {"latency_ms": round(body.observed_server_ms - source_end, 2),
                          "uncertainty_ms": round(uncertainty, 2), "clock_rtt_ms": body.clock_rtt_ms,
                          "clock_age_ms": body.clock_age_ms, "poll_interval_ms": body.poll_interval_ms}
        marker.listeners.remove(listener)
        row = self._append(marker, listener, status, **values)
        if not marker.listeners:
            self.markers.pop(body.marker_id, None)
        return row


def register_turn_latency(app, store, accounts):
    service = TurnLatency(store)
    store.turn_latency = service
    app.state.turn_latency = service
    router = APIRouter()

    def authorize(request, code, token):
        accounts.require(request)
        return store.authenticate(token, code).participant_id

    @router.get("/api/rooms/{code}/latency-clock")
    async def calibration(code: str, request: Request, token: str = Depends(bearer_token)):
        listener = authorize(request, code, token)
        store.rate_limit("latency-clock", listener, 60)
        return service.clock(code, listener)

    @router.get("/api/rooms/{code}/latency-observations")
    async def observations(code: str, request: Request, token: str = Depends(bearer_token)):
        listener = authorize(request, code, token)
        return service.report(code, listener)

    @router.post("/api/rooms/{code}/latency-observations")
    async def observation(code: str, body: LatencyObservation, request: Request, token: str = Depends(bearer_token)):
        listener = authorize(request, code, token)
        store.rate_limit("latency-observations", listener, 120)
        return service.observe(code, listener, body)

    app.include_router(router)
    return service
