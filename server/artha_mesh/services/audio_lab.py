"""Opt-in loopback-only WAV experiments. No provider or filesystem audio writes."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from .audio_screening import read_pcm_wav

MAX_WAV_BYTES = 1_024_000


def read_pcm(clip: bytes) -> bytes:
    try:
        return read_pcm_wav(clip)[0]
    except ValueError as exc:
        raise HTTPException(422, str(exc) or "Malformed WAV recording") from None


def audio_lab_router(config, store, runtime):
    router = APIRouter(prefix="/api/audio-lab")

    def permitted(request):
        if not config.local_audio_lab_enabled or config.mode == "live":
            raise HTTPException(403, "Audio lab requires the local no-provider launcher")
        if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "Audio lab is available only on this computer")
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in config.cors_origins:
            raise HTTPException(403, "Open the audio lab from the local application")

    @router.get("/status")
    async def status(request: Request):
        permitted(request)
        return {"enabled": True, **runtime.status()}

    @router.post("/analyze")
    async def analyze(request: Request, audio: UploadFile = File(...), consent: bool = Form(False)):
        try:
            permitted(request)
            if not consent:
                raise HTTPException(422, "Confirm permission to analyze this recording locally")
            store.rate_limit("audio-lab", "local", 12)
            clip = await audio.read(MAX_WAV_BYTES + 1)
            if len(clip) > MAX_WAV_BYTES:
                raise HTTPException(413, "WAV file exceeds the local upload limit")
            result = await runtime.analyze(read_pcm(clip))
            return {"schema_version": 1, "provider_calls": 0, "persisted": False,
                    "result": result.as_dict()}
        finally:
            await audio.close()

    return router
