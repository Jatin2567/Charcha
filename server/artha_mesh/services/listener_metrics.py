"""Bounded, participant-scoped diagnostics for a deliberately generated RTC tone.

The browser measures one interval with performance.now(). No browser wall clock
is subtracted from a server clock. These samples are not translation latency or
proof of sound leaving a physical speaker; even valid reports are client claims.
"""
from __future__ import annotations

import secrets
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import now
from ..store import Store
from .performance import percentile

MEASUREMENT = "request_to_decoded_probe_audio"
PROBE_TTL_SECONDS = 30.0
MAX_PROBE_SAMPLES = 200
MAX_PENDING_PER_LISTENER = 2
MAX_PENDING_PER_ROOM = 32


class ProbeReport(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    probe_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    status: Literal["detected", "timeout", "cancelled"] = "detected"
    elapsed_ms: float | None = Field(default=None, gt=0, le=30000, strict=True)
    poll_interval_ms: float = Field(default=100, ge=10, le=1000, strict=True)
    output_enabled: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def validate_detection(self):
        if self.status == "detected" and (self.elapsed_ms is None or not self.output_enabled):
            raise ValueError("A detection needs a finite interval and enabled playback")
        if self.status != "detected" and self.elapsed_ms is not None:
            raise ValueError("Unsuccessful probes do not have a latency measurement")
        return self


@dataclass
class PendingProbe:
    probe_id: str
    room_code: str
    listener_id: str
    expires_at: float
    started_at: float | None = None

    def public(self, current: float) -> dict:
        return {
            "probe_id": self.probe_id,
            "listener_id": self.listener_id,
            "track_name": f"probe:{self.probe_id}:{self.listener_id}",
            "measurement": MEASUREMENT,
            "expires_in_ms": max(0, round((self.expires_at - current) * 1000)),
        }


class ListenerMetrics:
    def __init__(self, store: Store):
        self.store = store
        self.pending: dict[str, PendingProbe] = {}
        self.samples: dict[str, deque[dict]] = {}

    def _append(self, probe: PendingProbe, status: str, **values):
        rows = self.samples.setdefault(probe.room_code, deque(maxlen=MAX_PROBE_SAMPLES))
        rows.append({
            "probe_id": probe.probe_id,
            "listener_id": probe.listener_id,
            "measurement": MEASUREMENT,
            "status": status,
            "elapsed_ms": None,
            "poll_interval_ms": None,
            "server_start_to_report_ms": None,
            "created_at": now().isoformat(),
            **values,
        })

    def _prune(self):
        current = time.monotonic()
        for probe_id, probe in list(self.pending.items()):
            if not self.store.is_active(probe.room_code, probe.listener_id):
                self.pending.pop(probe_id, None)
            elif probe.expires_at <= current:
                self.pending.pop(probe_id, None)
                if probe.started_at is not None:
                    self._append(probe, "expired")
        for code in list(self.samples):
            state = self.store.rooms.get(code)
            if state is None or state.expires_at <= time.time():
                self.samples.pop(code, None)

    def issue(self, token: str, code: str) -> dict:
        session = self.store.authenticate(token, code)
        self._prune()
        state = self.store.room(session.room_code)
        if state.room.mode == "demo":
            raise HTTPException(409, "Audio probes require a real local or live audio room")
        self.store.rate_limit("audio_probe_issue", f"{session.room_code}:{session.participant_id}", 6)
        room_probes = [p for p in self.pending.values() if p.room_code == session.room_code]
        if (len(room_probes) >= MAX_PENDING_PER_ROOM
                or sum(p.listener_id == session.participant_id for p in room_probes)
                >= MAX_PENDING_PER_LISTENER):
            raise HTTPException(429, "Finish the active audio probe before requesting another")
        current = time.monotonic()
        probe = PendingProbe(secrets.token_urlsafe(18), session.room_code,
                             session.participant_id, current + PROBE_TTL_SECONDS)
        self.pending[probe.probe_id] = probe
        return probe.public(current)

    def _owned(self, token: str, code: str, probe_id: str) -> PendingProbe:
        session = self.store.authenticate(token, code)
        self._prune()
        probe = self.pending.get(probe_id)
        if probe is None:
            raise HTTPException(404, "Audio probe is expired, completed or unknown")
        if probe.room_code != session.room_code or probe.listener_id != session.participant_id:
            raise HTTPException(403, "Audio probe belongs to another listener")
        return probe

    def start(self, token: str, code: str, probe_id: str) -> dict:
        probe = self._owned(token, code, probe_id)
        if probe.started_at is not None:
            raise HTTPException(409, "Audio probe was already started")
        probe.started_at = time.monotonic()
        return probe.public(probe.started_at)

    def record(self, token: str, code: str, report: ProbeReport) -> dict:
        probe = self._owned(token, code, report.probe_id)
        if probe.started_at is None:
            raise HTTPException(409, "Start the audio probe before reporting its result")
        self.store.rate_limit("audio_probe_report", f"{probe.room_code}:{probe.listener_id}", 12)
        self.pending.pop(probe.probe_id)
        self._append(
            probe, report.status,
            elapsed_ms=round(report.elapsed_ms, 2) if report.elapsed_ms is not None else None,
            poll_interval_ms=round(report.poll_interval_ms, 2),
            server_start_to_report_ms=round((time.monotonic() - probe.started_at) * 1000, 2),
        )
        return self.samples[probe.room_code][-1].copy()

    def snapshot(self, code: str) -> dict:
        """Caller must authenticate room membership before exposing this report."""
        self.store.room(code)
        self._prune()
        rows = list(self.samples.get(code.lower(), ()))
        elapsed = [row["elapsed_ms"] for row in rows if row["status"] == "detected"]
        return {
            "room_code": code.lower(),
            "generated_at": now().isoformat(),
            "measurement": {
                "boundary": MEASUREMENT,
                "clock": "single_browser_monotonic",
                "detection": "dedicated_probe_track_energy",
                "client_reported": True,
                "physical_speaker_output_measured": False,
                "translation_end_to_end_measured": False,
                "includes": ["start_request", "server_tone_queue", "rtc_receive", "browser_detection"],
                "excludes": ["microphone_capture", "stt", "translation", "tts", "physical_speaker_output"],
                "polling_note": "Polling and main-thread scheduling add detection delay; not a precision guarantee",
                "retention_limit": MAX_PROBE_SAMPLES,
            },
            "summary": {
                "sample_count": len(rows),
                "detected_count": len(elapsed),
                "failed_count": sum(row["status"] in {"timeout", "expired", "delivery_error"} for row in rows),
                "cancelled_count": sum(row["status"] == "cancelled" for row in rows),
                "p50_ms": percentile(elapsed, 0.5),
                "p95_ms": percentile(elapsed, 0.95),
            },
            "samples": [row.copy() for row in rows],
        }

    def fail(self, code: str, probe_id: str):
        """Internal emitter failure only; a completed client result wins the race."""
        probe = self.pending.get(probe_id)
        if probe is None or probe.room_code != code.lower() or probe.started_at is None:
            return
        self.pending.pop(probe_id, None)
        self._append(probe, "delivery_error")

    def close_room(self, code: str):
        for probe_id, probe in list(self.pending.items()):
            if probe.room_code == code:
                self.pending.pop(probe_id, None)
        self.samples.pop(code, None)
