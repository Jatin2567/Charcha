from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

import anyio
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import __version__
from .auth import bearer_token
from .config import Settings
from .errors import ProviderError
from .models import (
    LANGUAGES,
    ConfirmTurn,
    CreateRoom,
    DemoScenario,
    Event,
    JoinRoom,
    LeaveRoom,
    SubmitText,
    UpdateParticipant,
)
from .providers.demo import SAMPLES, DemoTranslator
from .providers.disabled import DisabledProviders
from .providers.evon import EvonTranslator
from .providers.gnani import GnaniSpeech
from .security import RequestBodyLimitMiddleware
from .services.performance import performance_snapshot
from .services.audio_lab import audio_lab_router
from .services.screening_runtime import ScreeningRuntime
from .services.listener_metrics import ListenerMetrics, ProbeReport
from .services.pipeline import Pipeline
from .services.readiness import ConferenceReadiness, readiness_snapshot
from .services.rooms import RoomService
from .services.usage import UsageGuard
from .services.voice import MAX_REFERENCE_BYTES, VoiceService
from .store import Consumer, Store, token_digest
from .transport.livekit import TransportManager


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    store = Store(config)
    screening = ScreeningRuntime(config)
    listener_metrics = ListenerMetrics(store)
    usage = UsageGuard(config)
    if config.mode == "transport":
        # Construct no provider clients even when a private .env contains real keys.
        speech = translator = DisabledProviders()
    else:
        speech = GnaniSpeech(config, usage)
        translator = DemoTranslator() if config.mode == "demo" else EvonTranslator(config, usage)
    pipeline = Pipeline(store, translator, speech)
    transport = TransportManager(store, speech, pipeline, screening)
    pipeline.transport = transport
    voices = VoiceService(store, speech)
    service = RoomService(store, pipeline, transport, voices, usage)

    async def cleanup():
        while True:
            await asyncio.sleep(30)
            await service.prune_expired()

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(cleanup())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            demo_tasks = []
            for state in store.rooms.values():
                if state.demo_task:
                    state.demo_task.cancel()
                    demo_tasks.append(state.demo_task)
            await asyncio.gather(*demo_tasks, return_exceptions=True)
            await pipeline.aclose()
            await transport.aclose()
            await speech.aclose()
            if hasattr(translator, "aclose"):
                await translator.aclose()
            store.voices.clear()
            store.sessions.clear()
            usage.close()

    app = FastAPI(title="Artha-Mesh", version=__version__, lifespan=lifespan)
    app.state.settings, app.state.store = config, store
    app.state.pipeline, app.state.transport = pipeline, transport
    app.state.service, app.state.voices = service, voices
    app.state.usage = usage
    app.state.screening = screening
    app.state.listener_metrics = listener_metrics
    app.include_router(audio_lab_router(config, store, screening))
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"], allow_credentials=False,
    )

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(ProviderError)
    async def provider_failure(request, error: ProviderError):
        return JSONResponse({"detail": error.message, "retryable": error.retryable}, status_code=502)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error: RequestValidationError):
        # Do not echo credentials, audio, or non-finite JSON inputs in errors.
        return JSONResponse({"detail": [
            {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
            for item in error.errors()
        ]}, status_code=422)

    @app.get("/api/health")
    async def health():
        if config.mode == "demo":
            providers = [{"name": name, "status": "demo", "detail": "Scripted local examples; no provider calls"}
                         for name in ["LiveKit", "Prisma STT", "Evon MT", "Timbre TTS"]]
        elif config.mode == "transport":
            providers = [{
                "name": "LiveKit", "status": "missing" if config.missing_transport_config() else "configured",
                "detail": "Local original-audio relay; connectivity is checked on room join",
            }] + [{"name": name, "status": "disabled", "detail": "Transport test makes no speech-provider calls"}
                  for name in ["Prisma STT", "Evon MT", "Timbre TTS"]]
        else:
            def configured(name, ready, detail):
                return {"name": name, "status": "configured" if ready else "missing", "detail": detail}
            providers = [
                configured("LiveKit", bool(config.livekit_url and config.livekit_api_key.get_secret_value() and config.livekit_api_secret.get_secret_value()), "Configuration only; connection is verified on room join"),
                configured("Prisma STT", bool(config.gnani_api_key.get_secret_value()), "Streaming speech recognition; credentials unverified until used"),
                configured("Evon MT", bool(config.evon_base_url and config.evon_model), "Requires your hosted OpenAI-compatible Evon model endpoint"),
                configured("Timbre TTS", bool(config.gnani_api_key.get_secret_value()), "Stock and consented cloned synthesis; account access unverified"),
            ]
        return {"status": "ok", "mode": config.mode, "providers": providers,
                "languages": LANGUAGES, "version": __version__}

    @app.get("/api/demo/samples")
    async def demo_samples():
        return {"samples": SAMPLES, "simulated": True}

    @app.get("/api/usage")
    async def usage_summary():
        return usage.public_snapshot()

    @app.get("/api/readiness")
    async def readiness():
        return readiness_snapshot(config)

    @app.post("/api/rooms", status_code=201)
    async def create_room(body: CreateRoom, request: Request):
        await service.prune_expired()
        store.rate_limit("create", request.client.host if request.client else "unknown", 20)
        return store.create_room(body.title).room

    @app.get("/api/rooms/{code}")
    async def get_room(code: str):
        return store.room(code).room

    @app.post("/api/rooms/{code}/join")
    async def join_room(code: str, body: JoinRoom, request: Request):
        store.rate_limit("join", request.client.host if request.client else "unknown", 60)
        return await service.join(code.lower(), body)

    @app.post("/api/rooms/{code}/leave")
    async def leave_room(code: str, body: LeaveRoom, token: str = Depends(bearer_token)):
        await service.leave(code.lower(), body.participant_id, token)
        return {"ok": True}

    @app.patch("/api/rooms/{code}/participants/me")
    async def update_participant(code: str, body: UpdateParticipant, token: str = Depends(bearer_token)):
        return await service.update(code.lower(), body, token)

    @app.get("/api/rooms/{code}/transcript")
    async def transcript(code: str, token: str = Depends(bearer_token)):
        store.authenticate(token, code)
        state = store.room(code)
        return {"turns": state.turns, "metrics": state.metrics}

    @app.get("/api/rooms/{code}/performance")
    async def performance(code: str, token: str = Depends(bearer_token)):
        store.authenticate(token, code)
        return performance_snapshot(store.room(code))

    @app.get("/api/rooms/{code}/conference-readiness", response_model=ConferenceReadiness)
    async def room_conference_readiness(code: str, token: str = Depends(bearer_token)):
        return service.conference_readiness(code.lower(), token)

    @app.get("/api/rooms/{code}/screening")
    async def screening_report(code: str, token: str = Depends(bearer_token)):
        store.authenticate(token, code)
        state = store.room(code)
        return {**screening.status(), "latest": state.screening_latest,
                "samples": list(state.screening_samples), "experimental": True,
                "limitation": "A model flag is not proof of a deepfake. Indian-language accuracy is unverified."}

    @app.post("/api/rooms/{code}/audio-probes", status_code=201)
    async def issue_probe(code: str, token: str = Depends(bearer_token)):
        return listener_metrics.issue(token, code)

    @app.post("/api/rooms/{code}/audio-probes/{probe_id}/start", status_code=202)
    async def start_probe(code: str, probe_id: str, token: str = Depends(bearer_token)):
        store.authenticate(token, code)
        audio_room = transport.rooms.get(code.lower())
        if not audio_room or audio_room.closed or audio_room.disconnected:
            raise HTTPException(409, "Join a connected audio room before starting a receiver probe")
        challenge = listener_metrics.start(token, code, probe_id)
        try:
            async with asyncio.timeout(9):
                await audio_room.send_probe(challenge)
        except (ProviderError, asyncio.CancelledError):
            listener_metrics.fail(code.lower(), probe_id)
            raise
        except Exception:
            listener_metrics.fail(code.lower(), probe_id)
            raise ProviderError("Receiver tone delivery timed out or failed; reconnect and try again", False) from None
        return {"started": True, "provider_calls": 0}

    @app.post("/api/rooms/{code}/audio-probes/report")
    async def report_probe(code: str, body: ProbeReport, token: str = Depends(bearer_token)):
        return listener_metrics.record(token, code, body)

    @app.get("/api/rooms/{code}/audio-probes")
    async def probe_report(code: str, token: str = Depends(bearer_token)):
        store.authenticate(token, code)
        return listener_metrics.snapshot(code)

    @app.post("/api/rooms/{code}/text", status_code=202)
    async def text_turn(code: str, body: SubmitText, token: str = Depends(bearer_token)):
        session = store.authenticate(token, code)
        store.rate_limit("text", token_digest(token), 30)
        state = store.room(code)
        speaker = next(p for p in state.room.participants if p.id == session.participant_id)
        return {"utterance_id": await pipeline.submit(state, speaker, body.text)}

    @app.post("/api/rooms/{code}/demo")
    async def run_demo(code: str, body: DemoScenario, token: str = Depends(bearer_token)):
        store.authenticate(token, code)
        store.rate_limit("demo", token_digest(token), 5)
        await service.start_demo(code.lower())
        return {"ok": True}

    @app.post("/api/voice-profiles", status_code=201)
    async def enroll_voice(
        audio_file: UploadFile = File(...), name: str = Form(...),
        consent: bool = Form(False), owner_token: str = Form(...),
    ):
        # Authenticate before reading the file. Only at most limit+1 bytes enter memory.
        store.authenticate(owner_token)
        try:
            clip = await audio_file.read(MAX_REFERENCE_BYTES + 1)
            if len(clip) > MAX_REFERENCE_BYTES:
                raise HTTPException(413, "Reference recording must be no larger than 10 MiB")
            return await voices.enroll(clip, audio_file.content_type or "", name, consent, owner_token)
        finally:
            await audio_file.close()

    @app.delete("/api/voice-profiles/{profile_id}")
    async def delete_voice(profile_id: str, token: str = Depends(bearer_token)):
        await service.delete_voice(profile_id, token)
        return {"ok": True}

    @app.post("/api/rooms/{code}/confirmations")
    async def confirm(code: str, body: ConfirmTurn, token: str = Depends(bearer_token)):
        session = store.authenticate(token, code)
        state = store.room(code)
        turn = next((turn for turn in state.turns if turn.id == body.utterance_id), None)
        if not turn:
            raise HTTPException(404, "Utterance not found")
        if turn.status != "complete":
            raise HTTPException(409, "Wait for interpretation to complete before confirming")
        if session.participant_id not in turn.confirmed_by:
            turn.confirmed_by.append(session.participant_id)
        state.broadcast("confirmation.updated", {"utterance_id": turn.id, "confirmed_by": turn.confirmed_by})
        return {"confirmed_by": turn.confirmed_by}

    @app.websocket("/api/rooms/{code}/events")
    async def events(websocket: WebSocket, code: str, token: str = ""):
        protocols = [value.strip() for value in websocket.headers.get("sec-websocket-protocol", "").split(",")]
        # Browsers send credentials in an upgrade header, never in logged URLs.
        if not token:
            token = next((value.removeprefix("artha-token.") for value in protocols if value.startswith("artha-token.")), "")
        origin = websocket.headers.get("origin")
        if origin and origin.rstrip("/") not in config.cors_origins:
            await websocket.close(code=1008)
            return
        try:
            store.authenticate(token, code)
        except HTTPException:
            await websocket.close(code=1008)
            return
        state = store.room(code)
        # Bound concurrent consumers as well as connection attempts per credential.
        digest = token_digest(token)
        try:
            store.rate_limit("events", digest, 20)
        except HTTPException:
            await websocket.close(code=1008)
            return
        if sum(c.owner_digest == digest for c in state.consumers) >= 4:
            await websocket.close(code=1008)
            return
        consumer = Consumer(asyncio.Queue(maxsize=config.event_queue_size), owner_digest=digest)
        state.consumers.add(consumer)

        async def sender():
            while True:
                try:
                    event = await asyncio.wait_for(consumer.queue.get(), timeout=20)
                    store.authenticate(token, code)
                    await websocket.send_json(event)
                except TimeoutError:
                    store.authenticate(token, code)
                    await websocket.send_json(Event(type="heartbeat", payload={}).model_dump(mode="json"))

        async def receiver():
            while True:
                # Receive disconnects promptly even in a room with no new events.
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return

        tasks = []
        try:
            await websocket.accept(subprotocol="artha-events" if "artha-events" in protocols else None)
            snapshot = Event(type="room.snapshot", payload={
                "room": state.room.model_dump(mode="json"),
                "turns": [turn.model_dump(mode="json") for turn in state.turns],
                "metrics": state.metrics.model_dump(mode="json"),
                "screening": state.screening_latest,
                "screening_status": screening.status(),
            })
            await websocket.send_json(snapshot.model_dump(mode="json"))
            tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver()),
                     asyncio.create_task(consumer.overflow.wait())]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        finally:
            state.consumers.discard(consumer)
            for task in tasks:
                task.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.gather(*tasks, return_exceptions=True)
                with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                    await websocket.close(code=1013 if consumer.overflow.is_set() else 1000)

    return app


app = create_app()
