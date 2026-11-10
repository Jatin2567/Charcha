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
from .accounts import LOGOUT, PUBLIC, Accounts
from .admission import admission_router, admission_status
from .auth import bearer_token
from .config import Settings
from .errors import ProviderError
from .models import (
    LANGUAGES,
    ConfirmTurn,
    CorrectTurn,
    CreateRoom,
    DemoScenario,
    Event,
    JoinRoom,
    LeaveRoom,
    ScreeningChange,
    SubmitText,
    UpdateParticipant,
)
from .providers.demo import SAMPLES, DemoTranslator
from .providers.disabled import DisabledProviders
from .providers.evon import EvonTranslator
from .providers.gnani import GnaniSpeech
from .security import RequestBodyLimitMiddleware
from .services.performance import performance_snapshot
from .services.performance_history import PerformanceHistory, ConnectionSnapshot, principal_key
from .services.turn_latency import register_turn_latency
from .services.audio_lab import audio_lab_router
from .services.screening_runtime import ScreeningRuntime
from .services.listener_metrics import ListenerMetrics, ProbeReport
from .services.pipeline import Pipeline
from .services.readiness import ConferenceReadiness, readiness_snapshot
from .services.rooms import RoomService
from .services.usage import UsageGuard
from .services.voice import MAX_REFERENCE_BYTES, VoiceService
from .services.meeting_engine import MeetingEngineLifecycle
from .services.reviewer_resources import ReviewerResources, RoutedSpeech, RoutedTranslator, RoutedUsage
from .store import Consumer, Store, account_deadline, account_session, account_history_key, token_digest
from .transport.livekit import TransportManager


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    store = Store(config)
    accounts = Accounts(config, store)
    screening = ScreeningRuntime(config)
    listener_metrics = ListenerMetrics(store)
    history = PerformanceHistory(config, listener_metrics)
    def host_room_expiry(code):
        state = store.rooms.get(code)
        registry = getattr(store, "reviewer_resources", None)
        if registry and code in registry.rooms and not registry.valid(code):
            return None
        return state.expires_at if state and state.host_funded else None

    usage = UsageGuard(config, host_room_expiry=host_room_expiry)
    if config.mode == "transport":
        # Construct no provider clients even when a private .env contains real keys.
        speech = translator = DisabledProviders()
    else:
        speech = GnaniSpeech(config, usage)
        translator = DemoTranslator() if config.mode == "demo" else EvonTranslator(config, usage)
    reviewer_resources = ReviewerResources(config, store, accounts, usage, speech, translator)
    store.reviewer_resources = reviewer_resources
    store.resource_settings = reviewer_resources.settings_for
    routed_usage = RoutedUsage(reviewer_resources)
    if config.mode == "live":
        speech = RoutedSpeech(reviewer_resources, routed_usage)
        translator = RoutedTranslator(reviewer_resources)
    pipeline = Pipeline(store, translator, speech)
    transport = TransportManager(store, speech, pipeline, screening)
    pipeline.transport = transport
    voices = VoiceService(store, speech)
    service = RoomService(store, pipeline, transport, voices, routed_usage, history)
    meeting_engine = MeetingEngineLifecycle(store, transport, getattr(translator, "engine", None),
        resolve_engine=reviewer_resources.engine_for,
        is_authorized=lambda state: reviewer_resources.valid(state.room.code)
            if state.room.code in reviewer_resources.rooms else state.host_funded)
    reviewer_resources.service, reviewer_resources.lifecycle = service, meeting_engine
    service.reviewer_resources = reviewer_resources

    async def cleanup():
        while True:
            await asyncio.sleep(30)
            accounts.prune()
            await reviewer_resources.prune()
            await service.prune_expired()

    async def save_reports():
        while True:
            await asyncio.sleep(5)
            for state in list(store.rooms.values()):
                if state.performance_owners and any(store.is_active(state.room.code, p.id) for p in state.room.participants):
                    service.save_performance(state)

    @asynccontextmanager
    async def lifespan(app):
        await history.start()
        task = asyncio.create_task(cleanup())
        engine_task = asyncio.create_task(meeting_engine.run())
        history_task = asyncio.create_task(save_reports())
        try:
            yield
        finally:
            task.cancel()
            engine_task.cancel()
            history_task.cancel()
            await asyncio.gather(task, engine_task, history_task, return_exceptions=True)
            await reviewer_resources.aclose()
            demo_tasks = []
            for state in store.rooms.values():
                if state.demo_task:
                    state.demo_task.cancel()
                    demo_tasks.append(state.demo_task)
            await asyncio.gather(*demo_tasks, return_exceptions=True)
            await pipeline.aclose()
            for state in list(store.rooms.values()):
                service.save_performance(state, interrupted=True)
            await history.close()
            await transport.aclose()
            await voices.aclose()
            await speech.aclose()
            if hasattr(translator, "aclose"):
                await translator.aclose()
            store.voices.clear()
            store.sessions.clear()
            usage.close()

    app = FastAPI(title="Charcha", version=__version__, lifespan=lifespan)
    app.state.settings, app.state.store = config, store
    app.state.pipeline, app.state.transport = pipeline, transport
    app.state.service, app.state.voices = service, voices
    app.state.meeting_engine = meeting_engine
    app.state.accounts = accounts
    app.state.reviewer_resources = reviewer_resources
    app.include_router(accounts.router(service))
    app.include_router(reviewer_resources.router())
    app.include_router(admission_router(store, accounts, service))
    app.state.usage = usage
    app.state.screening = screening
    app.state.listener_metrics = listener_metrics
    app.state.performance_history = history
    turn_latency = register_turn_latency(app, store, accounts)
    app.include_router(audio_lab_router(config, store, screening))
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"], allow_credentials=False,
    )

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        identity = accounts.current(request)
        marker = account_session.set(identity.key if identity else None)
        deadline = account_deadline.set(identity.expires if identity else 0)
        history_identity = account_history_key.set(principal_key(accounts.issuer, identity.subject) if identity else None)
        try:
            protected = request.url.path.startswith("/api/") and request.url.path not in PUBLIC
            if protected and not identity:
                response = JSONResponse({"detail": "Sign in to continue"}, status_code=401)
            elif (protected or request.url.path == LOGOUT) and request.method not in ("GET", "HEAD", "OPTIONS") and (
                (request.headers.get("origin") and request.headers["origin"] != accounts.origin)
                or (request.cookies and not request.headers.get("origin") and request.headers.get("x-charcha-request", request.headers.get("x-artha-request")) != "1")
            ):
                response = JSONResponse({"detail": "Request origin could not be verified"}, status_code=403)
            else:
                response = await call_next(request)
        finally:
            account_session.reset(marker)
            account_deadline.reset(deadline)
            account_history_key.reset(history_identity)
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
        who = accounts.require(request)
        if not accounts.can_host(who):
            raise HTTPException(403, "Only the designated host or an invited reviewer can create a meeting")
        reviewer_mode = body.resource_mode == "reviewer"
        if config.mode == "live" and body.audio_mode != "original" and who.email != accounts.host_email() and not reviewer_mode:
            raise HTTPException(409, "Choose your resources on the reviewer page before creating a meeting")
        if reviewer_mode and (config.mode != "live" or body.audio_mode == "original"):
            raise HTTPException(409, "Reviewer resources are for live interpreted meetings")
        budget = usage.host_policy() if config.mode == "live" and body.audio_mode != "original" and not reviewer_mode else None
        state = store.create_room(body.title, body.audio_mode,
                                  host_funded=reviewer_mode or bool(budget and budget["host_email"] == who.email))
        state.owner = who.subject
        if reviewer_mode:
            try:
                await reviewer_resources.bind(who, state)
            except BaseException:
                store.rooms.pop(state.room.code, None)
                raise
        return state.room

    @app.get("/api/rooms/{code}")
    async def get_room(code: str, request: Request):
        state = store.room(code)
        return state.room if accounts.require(request).subject == state.owner else state.room.model_copy(update={"participants": []})

    @app.post("/api/rooms/{code}/join")
    async def join_room(code: str, body: JoinRoom, request: Request):
        store.rate_limit("join", request.client.host if request.client else "unknown", 60)
        who, state = accounts.require(request), store.room(code)
        status = admission_status(state, who)
        if status == "host":
            return {**await service.join(code.lower(), body), "is_host": True}
        if status != "approved":
            raise HTTPException(403, "The host must approve your request before you can join")
        entry = state.admissions[who.subject]
        entry["status"] = "joining"
        try:
            member = await service.join(code.lower(), body)
        except BaseException:
            entry["status"] = "approved"
            raise
        entry.update(status="joined", participant_id=member["participant"].id)
        return {**member, "is_host": False}

    @app.post("/api/rooms/{code}/connection")
    async def room_connection(code: str, request: Request, token: str = Depends(bearer_token)):
        who = accounts.require(request)
        member = service.connection(code.lower(), token)
        return {**member, "is_host": who.subject == store.room(code).owner}

    @app.post("/api/rooms/{code}/leave")
    async def leave_room(code: str, body: LeaveRoom, token: str = Depends(bearer_token)):
        await service.leave(code.lower(), body.participant_id, token)
        state = store.room(code)
        for sub, entry in list(state.admissions.items()):
            if entry.get("participant_id") == body.participant_id:
                del state.admissions[sub]
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
        seat = store.authenticate(token, code)
        state = store.room(code)
        return {**performance_snapshot(state), "turn_latency": turn_latency.report(code, seat.participant_id),
                "persistence": history.status(account_history_key.get(), state.room.id)}

    @app.get("/api/account/call-performance")
    async def current_call_performance(request: Request):
        who = accounts.require(request)
        principal = principal_key(accounts.issuer, who.subject)
        # Stable account ownership survives logout and a new browser session.
        for seat in reversed(store.sessions.values()):
            state = store.rooms.get(seat.room_code)
            if (state and state.performance_owners.get(seat.participant_id) == principal
                    and store.is_active(seat.room_code, seat.participant_id)):
                # A pending snapshot remains available if the disk is temporarily
                # busy; persistence status distinguishes it from committed data.
                try:
                    saved = await history.read_get(state.room.id, principal)
                except HTTPException as exc:
                    if exc.status_code not in (404, 503):
                        raise
                    saved = {"report_id":state.room.id, "title":state.room.title,
                             "participant_ids":[pid for pid, owner in state.performance_owners.items() if owner == principal],
                             "persistence":history.status(principal, state.room.id)}
                listener_report = turn_latency.report(state.room.code)
                own_ids = {pid for pid, owner in state.performance_owners.items() if owner == principal}
                listener_report["samples"] = [row for row in listener_report["samples"] if row["listener_id"] in own_ids]
                return {**saved, **performance_snapshot(state), "turn_latency": listener_report,
                        "view": "live", "participant_id": seat.participant_id}
        return await history.read_latest(principal)

    @app.get("/api/account/performance-history")
    async def performance_history(request: Request):
        who = accounts.require(request)
        principal = principal_key(accounts.issuer, who.subject)
        reports = await history.read_list(principal)
        return {"reports":reports, "retention_days": history.retention_days, "list_limit":100,
                "persistence":history.status(principal)}

    @app.get("/api/account/performance-history/{report_id}")
    async def saved_performance(report_id: str, request: Request):
        who = accounts.require(request)
        return await history.read_get(report_id, principal_key(accounts.issuer, who.subject))

    @app.post("/api/rooms/{code}/connection-metrics")
    async def save_connection_metrics(code: str, body: ConnectionSnapshot, token: str = Depends(bearer_token)):
        seat = store.authenticate(token, code)
        store.rate_limit("connection-metrics", seat.participant_id, 30)
        principal = account_history_key.get()
        state = store.room(code)
        queued = history.enqueue_connection(state, seat.participant_id, principal, body)
        return {"queued":queued, "persistence":history.status(principal, state.room.id)}

    @app.get("/api/rooms/{code}/conference-readiness", response_model=ConferenceReadiness)
    async def room_conference_readiness(code: str, token: str = Depends(bearer_token)):
        return service.conference_readiness(code.lower(), token)

    @app.get("/api/rooms/{code}/engine")
    async def engine_status(code: str, token: str = Depends(bearer_token)):
        store.authenticate(token, code)
        engine = reviewer_resources.engine_for(code)
        return engine.status() if engine else {"state": "external"}

    def preparation_status(code, who):
        state = store.room(code)
        if who.subject != state.owner and admission_status(state, who) not in {"approved", "joining", "joined"}:
            raise HTTPException(403, "The meeting host must admit you before you can view preparation")
        available = bool(state.room.mode == "live" and state.room.engine_on_demand)
        status = meeting_engine.status(code)
        return {**status, "available": available,
                "can_prepare": available and who.subject == state.owner and accounts.can_host(who),
                "detail": ("Preparation contacts the selected model endpoint and may use compute credits. Readiness checks do not synthesize speech."
                           if available else "This meeting uses original audio or an externally managed interpretation endpoint; on-demand preparation is unavailable.")}

    @app.get("/api/rooms/{code}/preparation")
    async def preparation(code: str, request: Request):
        return preparation_status(code.lower(), accounts.require(request))

    @app.post("/api/rooms/{code}/preparation")
    async def prepare_meeting(code: str, request: Request):
        code, who = code.lower(), accounts.require(request)
        status = preparation_status(code, who)
        if not status["can_prepare"]:
            raise HTTPException(403, "Only the authorized meeting host can prepare interpretation")
        store.rate_limit("prepare", who.subject, 6)
        meeting_engine.prepare(code, account_deadline=who.expires,
            authorization_check=lambda: reviewer_resources.account_valid(who)
                and (reviewer_resources.valid(code) if code in reviewer_resources.rooms else accounts.shared_resources_allowed(who)))
        return preparation_status(code, who)

    @app.delete("/api/rooms/{code}/preparation")
    async def cancel_preparation(code: str, request: Request):
        code, who = code.lower(), accounts.require(request)
        state = store.room(code)
        if who.subject != state.owner:
            raise HTTPException(403, "Only the meeting host can cancel preparation")
        meeting_engine.cancel_preparation(code)
        return preparation_status(code, who)

    @app.get("/api/account/interpretation-engine")
    async def account_engine_status(request: Request):
        accounts.require(request)
        engine = getattr(translator, "engine", None)
        return engine.status() if engine else {"state": "external"}

    @app.post("/api/rooms/{code}/engine")
    async def start_engine(code: str, token: str = Depends(bearer_token)):
        session = store.authenticate(token, code)
        state = store.room(code)
        engine = reviewer_resources.engine_for(code)
        if not state.host_funded or not state.room.engine_on_demand or not engine:
            raise HTTPException(409, "On-demand interpretation is unavailable in this meeting")
        # A seat alone does not hold compute; media must be connected to a live meeting.
        store.rate_limit("engine", session.participant_id, 6)
        meeting_engine.sync()
        if code not in engine.meeting_rooms:
            raise HTTPException(409, "Connect your meeting audio before starting interpretation")
        engine.begin()
        return engine.status()

    @app.get("/api/rooms/{code}/screening")
    async def screening_report(code: str, token: str = Depends(bearer_token)):
        store.authenticate(token, code)
        state = store.room(code)
        return {**screening.room_status(state.room), "latest": state.screening_latest,
                "samples": list(state.screening_samples), "experimental": True,
                "limitation": "A model flag is not proof of a deepfake. Indian-language accuracy is unverified."}

    @app.patch("/api/rooms/{code}/screening")
    async def change_screening(code: str, change: ScreeningChange, request: Request, token: str = Depends(bearer_token)):
        store.authenticate(token, code)
        state = store.room(code)
        if state.owner != accounts.require(request).subject:
            raise HTTPException(403, "Only the meeting host can change VoiceShield")
        if not state.room.screening_switchable:
            raise HTTPException(409, "On-demand VoiceShield is unavailable in this room")
        if change.mode == "monitor" and not screening.screener.status()["ready"]:
            raise HTTPException(503, "VoiceShield could not load its detector")
        if change.mode != state.room.screening_mode:
            store.rate_limit("screening-toggle", state.room.code, 30)
            state.room.screening_mode = change.mode
            rtc_room = transport.rooms.get(state.room.code)
            if rtc_room:
                rtc_room.reset_screening_windows()
            state.screening_latest.clear()
            state.broadcast("screening.changed", {"status": screening.room_status(state.room)})
        return screening.room_status(state.room)

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

    @app.post("/api/rooms/{code}/turns/{original_id}/correct", status_code=202)
    async def correct_turn(code: str, original_id: str, body: CorrectTurn, token: str = Depends(bearer_token)):
        session = store.authenticate(token, code)
        state = store.room(code)
        original = next((t for t in state.turns if t.id == original_id), None)
        if not original:
            raise HTTPException(404, "Turn not found")
        if original.speaker_id != session.participant_id:
            raise HTTPException(403, "Only the speaker can correct their words")
        store.rate_limit("text", token_digest(token), 30)
        speaker = next(p for p in state.room.participants if p.id == session.participant_id)
        # Corrections are entered in the original speaking language even after a language change.
        source = speaker.model_copy(update={"language": original.source_language})
        return {"utterance_id": await pipeline.submit(state, source, body.text, replaces=original)}

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
        if turn.superseded_by:
            raise HTTPException(409, "This message was corrected. Confirm the latest version.")
        if turn.status != "complete":
            raise HTTPException(409, "Wait for interpretation to complete before confirming")
        if turn.listeners_recorded or turn.replaces_id:
            if session.participant_id not in turn.listeners:
                raise HTTPException(403, "Only listeners present for this message can confirm understanding")
            listener = next(p for p in state.room.participants if p.id == session.participant_id)
            if listener.language != turn.source_language and not turn.translations.get(listener.language):
                raise HTTPException(409, "This message is unavailable in your listening language")
        else:
            raise HTTPException(409, "The listener list was not recorded for this older message; ask for a new message")
        if session.participant_id not in turn.confirmed_by:
            turn.confirmed_by.append(session.participant_id)
        state.broadcast("confirmation.updated", {"utterance_id": turn.id, "confirmed_by": turn.confirmed_by})
        return {"confirmed_by": turn.confirmed_by}

    @app.websocket("/api/rooms/{code}/events")
    async def events(websocket: WebSocket, code: str, token: str = ""):
        protocols = [value.strip() for value in websocket.headers.get("sec-websocket-protocol", "").split(",")]
        # Browsers send credentials in an upgrade header, never in logged URLs.
        if not token:
            token = next((value.removeprefix("charcha-token.") for value in protocols if value.startswith("charcha-token.")), "")
        origin = websocket.headers.get("origin")
        if origin and origin.rstrip("/") not in (*config.cors_origins, accounts.origin):
            await websocket.close(code=1008)
            return
        def authorize_socket():
            who = accounts.require(websocket)
            account_session.set(who.key)
            store.authenticate(token, code)

        try:
            authorize_socket()
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
                    authorize_socket()
                    await websocket.send_json(event)
                except TimeoutError:
                    authorize_socket()
                    await websocket.send_json(Event(type="heartbeat", payload={}).model_dump(mode="json"))

        async def receiver():
            while True:
                # Receive disconnects promptly even in a room with no new events.
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return

        tasks = []
        try:
            await websocket.accept(subprotocol="charcha-events" if "charcha-events" in protocols else None)
            snapshot = Event(type="room.snapshot", payload={
                "room": state.room.model_dump(mode="json"),
                "turns": [turn.model_dump(mode="json") for turn in state.turns],
                "metrics": state.metrics.model_dump(mode="json"),
                "screening": state.screening_latest,
                "screening_status": screening.room_status(state.room),
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
