# Artha-Mesh Track B implementation contract

Workspace: `outputs/artha-mesh`. Frontend owns `web/`; backend owns `server/artha_mesh/` and `server/pyproject.toml`; quality owns `server/tests/`, `evaluation/`, and `docs/ARCHITECTURE.md`. Root owns infrastructure, README and integration fixes.

## Product

Meet-inspired, carefully designed Indic audio interpretation. Hindi (`hi`), Tamil (`ta`), Bengali (`bn`), English (`en`). Home, prejoin, meeting, recap/history, voice studio, settings/setup. Two modes: clearly labelled local demonstration (scripted examples, never represented as live AI) and real LiveKit + Prisma + Evon-compatible MT + Timbre/voice-clone. No Track A detector or invented security/sovereignty claims.

## HTTP API (JSON snake_case)

Base `/api`; default local backend port 8000 (development launcher selects a free fallback when needed). Auth for room-member operations is `Authorization: Bearer <session_token>`. Room codes are unguessable invitations, not user account identities. Do not log credentials.

- GET `/health` -> `{status:"ok", mode:"demo"|"live", providers:[{name,status,detail}], languages:[{code,name,native_name}], version}`. No secret values.
- POST `/rooms` `{title:string}` -> Room.
- GET `/rooms/{code}` -> public Room with participants (no transcripts/tokens).
- POST `/rooms/{code}/join` `{name,language:"hi"|"ta"|"bn"|"en",voice_mode:"standard"|"cloned",voice_profile_id?:string,consent:boolean}` -> `{room,participant,session_token,livekit:null|{url,token,agent_identity}}`.
- POST `/rooms/{code}/leave` `{participant_id}` + bearer -> `{ok:true}`.
- PATCH `/rooms/{code}/participants/me` `{language?,voice_mode?,voice_profile_id?,muted?}` + bearer -> Participant. Member only; voice clone needs enrollment consent.
- GET `/rooms/{code}/transcript` + bearer -> `{turns:Turn[],metrics:Metrics}`.
- POST `/rooms/{code}/text` `{text:string}` + bearer -> `{utterance_id}`. Real MT/TTS in live mode; only known sample dictionary in demo. Not a fake speech recognizer.
- POST `/rooms/{code}/demo` `{scenario:"trade"}` + bearer -> `{ok:true}`. Creates explicitly simulated participants and runs canned hi/ta/bn turns through event stream; demo mode only.
- POST `/voice-profiles` multipart `audio_file`, `name`, `consent=true`, `owner_token` (a room membership token) -> `{id,name,created_at,mode:"demo"|"live"}`. Server stores session-scoped embedding, not raw clip. Validate MIME/size/duration; documented Gnani reference 5–30s of clean spoken audio. Never return embedding to browser.
- DELETE `/voice-profiles/{id}` + bearer -> `{ok:true}` owner only.
- POST `/rooms/{code}/confirmations` `{utterance_id}` + bearer -> `{confirmed_by:string[]}` (every human participant confirms own understanding; no automatic order placement).

Room `{id,code,title,created_at,mode,participants:Participant[]}`.
Participant `{id,name,language,voice_mode,muted:boolean,is_agent:boolean,is_demo:boolean,joined_at}`.
Turn `{id,speaker_id,speaker_name,source_language,text,created_at,translations:{[language]:string},confirmed_by:string[],status:"processing"|"complete"|"error"}`.
Metrics `{turns:number,stt_ms:number,mt_ms:number,tts_ms:number,total_ms:number,p50_ms:number,p95_ms:number,measurement:"server_pipeline"}`. Server timing is explicitly not measured receiver playback latency; demo metrics labelled simulated.

## Websocket events

`WS /api/rooms/{code}/events` with upgrade subprotocols `artha-events` and `artha-token.<session_token>`. The server selects `artha-events`, authenticates the header credential and validates the origin. The browser never puts its token in a URL. A legacy `?token=` parameter remains accepted for test/older-client compatibility and must be excluded from logs. Snapshot on connect, bounded queues, and removal of dead consumers are enforced.
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

Live audio always via LiveKit translated tracks, not browser TTS. Any browser speech synthesis in demo is optional, explicitly described as device voice, and language support is not guaranteed. Track names `translated:{speaker_id}:{target_language}`. Raw microphone publisher grants only `artha-agent-{room_id}` subscriber; agent publishes translations with participant-specific subscription permissions before publication. Agent filters its own generated tracks to avoid feedback. Same-language listeners get source forwarded as generated PCM agent track without MT. One STT stream per original speaker; one MT/TTS job per unique target language. Sequential source turns preserve order; target languages fan out concurrently with bounded queues, timeouts, cancellation on leave. Track routing never depends on frontend mute alone.

## Client behavior

`VITE_API_BASE_URL` optional, default `/api` through Vite proxy; `VITE_DEMO_MODE=true` permits standalone browser-only canned demo if backend unavailable. Backend mode wins when reachable. Browser-only demo is visibly labelled. Use `livekit-client` real adapter, device enumeration, microphone toggle, output mute, autoplay unlock, subscription filtering, copy invite, leave confirmation, transcript download, keyboard shortcuts, clean audio teardown. Never request mic on homepage. Membership credentials sessionStorage only. Exported recap can live in localStorage with explicit save/delete controls; do not persist tokens or voice references there.
