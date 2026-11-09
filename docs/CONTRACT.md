# Charcha Track B implementation contract

Workspace: `outputs/charcha`. Frontend owns `web/`; backend owns `server/charcha/` and `server/pyproject.toml`; quality owns `server/tests/`, `evaluation/`, and `docs/ARCHITECTURE.md`. Root owns infrastructure, README and integration fixes.

## Product

Meet-inspired Indic audio interpretation. Ten configurable languages: Hindi (`hi`), Tamil (`ta`), Bengali (`bn`), English (`en`), Telugu (`te`), Kannada (`kn`), Malayalam (`ml`), Marathi (`mr`), Gujarati (`gu`) and Punjabi (`pa`). Three explicit modes: `demo` for the original four-language scripted dictionary, `transport` for provider-free original audio, and `live` for configured LiveKit + Prisma + Evon-compatible MT + Timbre. Individual language directions still need live acceptance; cloned voices remain a later gate. Home, prejoin, meeting, Test lab, recap/history, voice studio and setup remain separated.

## HTTP API (JSON snake_case)

Base `/api`; default local backend port 8000 (development launcher selects a free fallback when needed). Auth for room-member operations is `Authorization: Bearer <session_token>`. Room codes are unguessable invitations, not user account identities. Do not log credentials.

- GET `/health` -> `{status:"ok", mode:"demo"|"transport"|"live", providers:[{name,status,detail}], languages:[{code,name,native_name}], version}`. No secret values.
- GET `/readiness` -> `{mode,generated_at,requirements:[{key,label,configured:boolean,required:boolean,group,detail}],provider_verification:"not_checked",deployment_checks:[{key,label,status:"manual",detail}]}`. Public redacted configuration presence, including in demo mode. Never returns keys, URLs, model values or credentials. `configured` indicates only a present setting; no paid connectivity probes run. Required keys: `CHARCHA_MODE` (configured only when live), `GNANI_API_KEY`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `EVON_BASE_URL`, `EVON_MODEL`. Optional selections: `EVON_API_KEY` (host-dependent authentication), `TIMBRE_MODEL`, `TIMBRE_VOICE`. Defaults can satisfy optional model/voice presence but do not prove entitlement.
- GET `/usage` -> global redacted UsageSnapshot below. Reading this endpoint does not contact a provider or consume credits. No browser endpoint edits/resets budgets.
- POST `/rooms` `{title:string}` -> Room.
- GET `/rooms/{code}` -> public Room with participants (no transcripts/tokens).
- POST `/rooms/{code}/join` `{name,language:"hi"|"ta"|"bn"|"en"|"te"|"kn"|"ml"|"mr"|"gu"|"pa",voice_mode:"standard"|"cloned",voice_profile_id?:string,consent:boolean}` -> `{room,participant,session_token,livekit:null|{url,token,agent_identity}}`. Join with a standard voice; enrollment is a separate session-owned operation. Dedicated Odia and code-mix codes are not accepted.
- POST `/rooms/{code}/leave` `{participant_id}` + bearer -> `{ok:true}`.
- PATCH `/rooms/{code}/participants/me` `{language?,voice_mode?,voice_profile_id?,muted?}` + bearer -> Participant. Member only; voice clone needs enrollment consent.
- GET `/rooms/{code}/transcript` + bearer -> `{turns:Turn[],metrics:Metrics}`.
- GET `/rooms/{code}/performance` + bearer -> PerformanceSnapshot below. Authenticated for the exact room; never includes conversation text, speaker names, voice references or credentials.
- POST `/rooms/{code}/text` `{text:string}` + bearer -> `{utterance_id}`. Real MT/TTS in live mode; only known sample dictionary in demo. Not a fake speech recognizer.
- POST `/rooms/{code}/demo` `{scenario:"everyday"}` + bearer -> `{ok:true}`. Creates explicitly simulated participants and runs canned community-centre plans and directions in hi/ta/bn through the event stream; demo mode only.
- POST `/voice-profiles` multipart `audio_file`, `name`, `consent=true`, `owner_token` (a room membership token) -> `{id,name,created_at,mode:"demo"|"live"}`. Server stores session-scoped embedding, not raw clip. Validate MIME/size/duration; documented Gnani reference 5–30s of clean spoken audio. Never return embedding to browser.
- DELETE `/voice-profiles/{id}` + bearer -> `{ok:true}` owner only.
- POST `/rooms/{code}/confirmations` `{utterance_id}` + bearer -> `{confirmed_by:string[]}` (every human participant confirms their own understanding; confirmation does not perform the spoken request).

Room `{id,code,title,created_at,mode,participants:Participant[]}`.
Participant `{id,name,language,voice_mode,muted:boolean,is_agent:boolean,is_demo:boolean,joined_at}`.
Turn `{id,speaker_id,speaker_name,source_language,text,created_at,translations:{[language]:string},confirmed_by:string[],status:"processing"|"complete"|"error"}`.
Metrics `{turns:number,stt_ms:number,mt_ms:number,tts_ms:number,total_ms:number,p50_ms:number,p95_ms:number,measurement:"server_pipeline"}`. Server timing is explicitly not measured receiver playback latency; demo metrics labelled simulated.

## Credit usage snapshot

UsageSnapshot is `{mode,period:{date,reset_at},enforcement:{enabled:true,persistent:boolean,status:"ready"|"unavailable"|"demo",detail},resources:UsageResource[],billing:{balance_available:false,detail},approval:FlowApproval,programme:ProgrammeUsage}`.

`date` is a UTC `YYYY-MM-DD` date and `reset_at` is the following UTC midnight as ISO 8601. Each resource is `{key,label,unit,used:number|null,limit:number,remaining:number|null,utilization_percent:number|null,status:"available"|"warning"|"exhausted"|"unknown"}`. Resource keys are `stt_seconds`, `stt_connections`, `mt_requests`, `mt_characters`, `tts_requests`, `tts_characters`, `voice_enrollments`. Units respectively are `seconds`, `connections`, `requests`, `characters`, `requests`, `characters`, `enrollments`. Warning begins when the displayed rounded utilization reaches 80%; exhausted means no remaining units, including a zero cap. A cap lowered below current usage can display utilization above 100%, with remaining clamped at zero. Unavailable storage returns unknown counters (`used`, `remaining`, `utilization_percent` are null), and blocks live provider calls. Demo returns configured limits and zero used units without creating/writing a ledger. `persistent:true` means the live ledger was readable, not that provider credentials have been verified.

Counters are application reservations, not provider-billed usage, an account balance, or a rupee estimate. Failed/partial attempts remain counted. Caps apply globally across rooms per UTC day and survive API restarts using the metadata-only SQLite ledger. All resources for a request are atomically reserved before the external operation; zero daily limits block the feature. Paid adapters enforce these guards even outside HTTP routes. See `docs/CREDIT_CONTROLS.md` for settings, storage, concurrency and infrastructure billing boundaries. The endpoint never returns keys, private paths/URLs, models, room IDs, identities, transcripts, audio or embeddings. Reference pricing may include the fixed public Gnani pricing-page URL.

`FlowApproval` is `{required,status:"locked"|"approved"|"unavailable"|"demo",active_flow_id:string|null,expires_at:string|null,detail}`. An active flow also has explicit budgets; it does not imply unlimited account access. All writes to grants/balance evidence are local operator CLI actions, with no browser mutation endpoint. Flow and daily reservations commit in the same SQLite transaction.

`ProgrammeUsage` contains `source`, `unit:"INR"|"programme_credits"|null`, `balance`, `observed_at`, `automatic_sync:false`, a safe detail, optional reference pricing, and at most 50 flow records. Each record has an ID, allowlisted purpose, status/timestamps, seven-key integer `budgets`/`used` maps, optional numeric timing metrics, and optional manual before/after evidence. `balance_delta` and `credits_used` remain null until reconciled; the latter is populated only for observations actually in programme-credit units. Neither is a provider-verified invoice. Reference speech costs never automatically debit the balance.

The public route uses `UsageGuard.public_snapshot()`: manual financial amounts, units and observation times are hidden by default, including per-flow reconciliation. Explicit `USAGE_SHOW_PRIVATE_BALANCE=true` is supported only for an operator-controlled local API. Production generation forces it false; public financial reporting would need separate authentication. Unknown/offline/static-demo data must never appear as a known zero balance or an approved flow.

STT reserves one second and one connection attempt before connecting, then each additional connected second in advance, including idle/handshake time. It closes when the next second cannot be reserved. Muted speakers, speakers without an active different-language human listener, and same-language-only rooms open no recognizer. Same-language source forwarding continues; live captions/transcript are unavailable in that case. STT authentication/quota errors and exceeded transient retry ceilings stop automatic reconnects; toggling the microphone can explicitly restart only within persistent caps. MT/TTS/enrollment have no silent paid retry. Their shared admission queue has two active operations, up to sixteen waiting and a five-second admission timeout by default, with no units reserved while waiting. Live room lifetime defaults to 900 seconds; expiry requests human LiveKit removal on the periodic sweep, which can be delayed by provider/network failure.

## Performance measurements

PerformanceSnapshot is `{room_code,mode,generated_at,measurement,summary,samples:PerformanceSample[]}`.

`measurement` is `{boundary:"server_first_pcm",stt:"processing_to_transcript",total:"queue_to_first_pcm_plus_stt",receiver_playback_measured:false,retention_limit:1000}`.

PerformanceSample is `{id,utterance_id,source_language,target_language,input_kind:"audio"|"text",voice_mode:"standard"|"cloned",status:"complete"|"error"|"cancelled",measurement:"server_first_pcm"|"source_forwarded"|"simulated",queue_ms:number|null,stt_ms:number|null,mt_ms:number|null,tts_first_pcm_ms:number|null,total_ms:number|null,created_at,error_stage:string|null}`. `voice_mode` records the requested voice at submission, enabling standard/cloned comparisons without retaining reference identifiers. Timestamps use UTC ISO 8601. Rows appear in terminal completion order, oldest first. `error_stage` is `null` on success or one of `queue`, `delivery`, `mt`, `voice_reference`, `tts`, `playout`, `internal`. Errors retain stage only, never upstream response bodies.

`summary` is `{sample_count,success_count,error_count,cancelled_count,live_sample_count,forwarded_count,simulated_count,p50_ms:number|null,p95_ms:number|null,by_direction:[{source_language,target_language,sample_count,success_count,error_count,cancelled_count,live_sample_count,p50_ms:number|null,p95_ms:number|null}]}`. Counts describe only the retained window of up to 1000 terminal language branches, not lifetime room totals. One utterance can create several unique listener-language branches. Nearest-rank p50/p95 include only completed `server_first_pcm` branches with a first-PCM measurement; failures, cancellations, forwarded source audio and scripted demo rows are excluded. No samples yields `null`, not a fabricated zero. Legacy room metrics remain numeric for compatibility, with p50/p95 derived from the same valid branch window.

- Queue: final transcript/text submission to FIFO dequeue, measured with the server monotonic clock. Queued cancellation records its elapsed wait to cancellation.
- STT: server receipt of the vendor's `processing` event to receipt of that segment's final transcript. This is a processing proxy, not speech-end delay, full utterance duration, or a vendor-reported benchmark. Missing processing markers and typed text yield `null`.
- MT: elapsed translation request, including an unsuccessful request where it began. Same-language typed input bypasses MT and yields `null`.
- TTS first PCM: start of speech dispatch to the first PCM frame accepted by the LiveKit audio source. Includes connection/output creation and upstream time. Completion/planned audio duration is excluded.
- Total: final transcript/text enqueue to first PCM dispatch, plus the STT processing proxy when available. Includes queue wait. When an audio row has `stt_ms:null`, total covers only enqueue-to-first-PCM; the absent STT interval is not silently estimated. Typed rows also cover enqueue-to-first-PCM. It excludes earlier capture/VAD time and network/jitter/device playback after the server boundary. It must never be labelled true mouth-to-ear or listener playback latency. Compare equivalent input/voice modes and STT availability when interpreting aggregates.

Same-language microphone audio is continuously forwarded by the transport, not synthesized by the utterance pipeline. Its informational branch rows are labelled `source_forwarded` with all timings `null`; these rows do not claim measured forwarding latency. Demo rows are labelled `simulated` with timings `null`. Pipeline failure before first PCM leaves total/TTS first PCM `null`. A failure during playout can retain the already measured first-PCM values but is still excluded from success percentiles. Data is memory-only and disappears with the room/process; download before leaving if needed.

No listeners means no branch rows. On an all-forwarded, all-failed or no-listener turn, legacy numeric stage metrics reset to zero (unavailable), while historical successful percentiles remain; the PerformanceSnapshot is the authoritative source for nullable stage measurements.

## Websocket events

`WS /api/rooms/{code}/events` with upgrade subprotocols `charcha-events` and `charcha-token.<session_token>`. The server selects `charcha-events`, authenticates the header credential and validates the origin. The browser never puts its token in a URL. A legacy `?token=` parameter remains accepted for test/older-client compatibility and must be excluded from logs. Snapshot on connect, bounded queues, and removal of dead consumers are enforced.
Envelope `{id,type,timestamp,payload}`:

- `room.snapshot`: `{room,turns,metrics}`
- `participant.joined`: `{participant}`
- `participant.updated`: `{participant}`
- `participant.left`: `{participant_id}`
- `transcript.final`: `{turn:Turn}`
- `translation.ready`: `{utterance_id,speaker_id,speaker_name,source_language,target_language,text,latency_ms,voice_mode}`
- `pipeline.status`: `{speaker_id,stage:"listening"|"transcribing"|"translating"|"speaking"|"idle"|"error",utterance_id?:string}`
- `metrics.updated`: Metrics
- `confirmation.updated`: `{utterance_id,confirmed_by:string[]}`
- `pipeline.error`: `{message,utterance_id?:string,retryable:boolean}` (no secrets or upstream raw error bodies)
- `demo.complete`: `{}`

Live audio always via LiveKit translated tracks, not browser TTS. Any browser speech synthesis in demo is optional, explicitly described as device voice, and language support is not guaranteed. Track names `translated:{speaker_id}:{target_language}`. Raw microphone publisher grants only `charcha-agent-{room_id}` subscriber; agent publishes translations with participant-specific subscription permissions before publication. Agent filters its own generated tracks to avoid feedback. Same-language listeners get source forwarded as generated PCM agent track without MT. One STT stream per active original speaker with a different-language listener; one MT/TTS job per unique target language. Same-language-only audiences open no recognizer. Sequential source turns preserve order; target languages fan out concurrently with bounded queues, timeouts, cancellation on leave. Track routing never depends on frontend mute alone.

## Client behavior

`VITE_API_BASE_URL` optional, default `/api` through Vite proxy; `VITE_DEMO_MODE=true` permits standalone browser-only canned demo if backend unavailable. Backend mode wins when reachable. Browser-only demo is visibly labelled. Use `livekit-client` real adapter, device enumeration, microphone toggle, output mute, autoplay unlock, subscription filtering, copy invite, leave confirmation, transcript download, keyboard shortcuts, clean audio teardown. Never request mic on homepage. Membership credentials sessionStorage only. Exported recap can live in localStorage with explicit save/delete controls; do not persist tokens or voice references there.
