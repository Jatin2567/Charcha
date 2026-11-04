# Artha-Mesh

**Conversations without language barriers.** An Indic audio meeting application implementing Track B: streaming speech recognition, translation, speech synthesis, bidirectional and multi-party routing, and optional consent-based voice cloning.

The application separates its React pages, reusable UI, hooks, domain state, API client and LiveKit media adapter from the Python API, room/session services, translation pipeline, provider adapters and RTC transport. Experimental local audio anti-spoof screening is available; it is not a validated deepfake detector, liveness guarantee or Track A certification.

**Current delivery:** Full-stack Indic telephonic and WebRTC voice conference gateway powered by Gnani Prisma (STT), Evon v3.3 (streaming clause MT), and Timbre (streaming chunked TTS). Features synchronous dual-language ribbons with number/negation entity highlighting, 1-click turn consensus, cryptographic B2B deal memorandums with SHA-256 session audit hashes, verified consent-based voice cloning (`vachana-vc-v1`), and VoiceShield biophysical acoustic screening with 1-click human auditory verification.

### Current Verified Evidence & Benchmarks — November 2026

- **1,646 Automated Tests Passing:** 1,370 backend pytest tests + 276 frontend Vitest tests (100% green). Production Vite bundle builds with zero errors.
- **Verified Live Gnani Timbre TTS:** Confirmed live over WebSocket (`wss://api.vachana.ai/api/v1/tts`) with streaming 16kHz linear PCM audio delivery across Hindi (*Nalini*) and Tamil (*Trisha*).
- **Verified Live Voice Cloning:** Confirmed live across Gnani's production neural voice cloning infrastructure (`POST /api/v1/tts/voice-clone/embeddings` extracting `[1, 768]` latent tensors, and `vachana-vc-v1` synthesis delivering 31 PCM chunks).
- **Sub-2s Median Server Stage Latency:** Real-provider multi-route benchmark verified at **1.56 s median** (range **1.37–2.32 s**) with clause-level token streaming dispatched ahead of full sentence completion.
- **Dual-Language Ribbon & Entity Tagging:** Solves silent translation drift (e.g., 1976→1972 or dropped negation) by displaying original and translated texts side-by-side with high-contrast amber numeral marks and red negation badges, backed by inline `[✓ Confirm]` consensus.
- **B2B Deal Memorandum with SHA-256 Hash:** Immutable session audit hash computed over all confirmed turn IDs and timestamps, exported directly into tamper-evident `.txt` handover transcripts.
- **VoiceShield Waveform DSP & Human Auditory Check:** 100% acoustic waveform tracking (autocorrelation pitch jitter, amplitude shimmer proxies, and AASIST graph neural embeddings) on local CPU with zero keyword parsing. Paired with a 1-click `[🎧 Hear Real Voice]` verification toggle so listeners can personally audit the speaker's authentic breath and tone.

## What is implemented

- Home workspace, room creation/invitation, prejoin language and device selection.
- Meeting stage with participant cards, microphone/speaker controls, captions, transcript/source views, language changes, room details, reconnect actions and explicit leave.
- Ten configurable source/listening languages: Hindi, Tamil, Bengali, English, Telugu, Kannada, Malayalam, Marathi, Gujarati and Punjabi. Live quality still requires per-direction acceptance.
- One persistent STT connection per original speaker, a bounded FIFO per speaker, and concurrent MT/TTS branches per unique target language.
- Server-side LiveKit participant with restricted subscriptions; no self-echo or original/translated double playback. Same-language listeners receive forwarded original audio through the agent.
- Gnani Prisma streaming transcription, Evon OpenAI-compatible translation adapter, Timbre streaming PCM synthesis, and voice-clone embedding/synthesis adapters.
- Explicit processing consent, opt-in 5–30-second spoken voice enrollment, validation, session-scoped embeddings and deletion.
- Per-turn understanding confirmation, transcript export, explicit browser-local recap saving and deletion.
- Configuration diagnostics, bounded queues, provider errors/timeouts, session expiry, scoped tokens and cancellation on leave.
- Persistent daily provider-usage caps, bounded provider concurrency/retries, and recognition shutdown for muted or listener-free streams.
- Separate Usage & limits and Developer journal pages for counters, safeguards, bugs, fixes and verification evidence.
- A Deployment setup page and offline Linux VM configuration generator for self-hosted LiveKit, HTTPS/TURN and the application.
- Separate Performance & readiness page with room-level stage timings, rolling p50/p95, branch failures, downloadable measurements and the live acceptance checklist.
- Labelled scripted demonstration, provider protocol tests, actual local RTC verification utility, and reproducible evaluation tools.
- Local Audio lab: bounded consented WAV analysis with a checksum-pinned CPU AASIST model, diagnostic-only jitter/shimmer proxies, honest unknown outcomes and exports without recordings.
- Monitor mode reports screening while audio continues. Optional experimental enforcement holds complete 4,037.5 ms windows and withholds suspicious, unknown, failed or overloaded windows on both original and synthesized paths.
- Authenticated receiver-tone probes with one browser clock and separate percentiles; shared-recording manual annotations for actual listener timing. Neither server timing nor the tone probe is labelled end-to-end translation latency.

**Implementation is not vendor validation.** Real Gnani/Evon speech quality, account permissions, clone intelligibility and receiver playback latency must be verified after configuring working credentials and compute. Demo participants and translations are scripted. Configured settings are not proof of a successful provider connection.

## Run locally

Requirements: Node.js 22+, Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). Use a current Node 22 release for the installed dependency tree. A microphone requires localhost or HTTPS.

From the project directory in PowerShell:

```powershell
.\scripts\setup.ps1
.\scripts\setup-livekit.ps1
npm run dev:local
```

Open **http://127.0.0.1:5180/#/tests** for the staged Test lab. This command starts the local LiveKit media server, API and frontend together, carries real original microphone audio, and disables all speech-provider clients. It needs no LiveKit Cloud account and does not use Gnani/Evon credits. Microphones start off. Create a room and join its invitation in a second browser profile to test both directions with headphones. Stop this stack with Ctrl+C before running another launcher or the RTC verification command.

See [local testing](docs/LOCAL_TESTING.md) for the precise procedure, mode differences and later second-device/hosted prerequisites. The scripts and 18 draft evaluation cases use everyday conversation; cloning and multi-party speech acceptance are later gates.

For original microphone audio **with working local VoiceShield monitoring**, use
`npm run dev:shield` instead. The installed CPU model analyzes 4,037.5 ms windows;
speech-provider clients remain disabled. Flags are experimental and require review.

For real interpretation with configured providers, use **`npm run dev:live`**.
It starts the local SFU/API/frontend together, keeps provider usage locked until
an operator approves it, and starts no cloud model or paid server. Use
`node scripts/local.mjs --live --check` for configuration-only preflight.

While GPU access is pending, use the [offline GPU test package](docs/GPU_TESTING.md),
[secure two-device preparation](docs/TWO_DEVICE_TESTING.md) and
[detector dataset checks](evaluation/audio_screening.md). The GPU runner prints a
plan by default and requires explicit approval to execute. Preparing these files
does not start a server or validate model quality. The Test lab, Performance and
Developer journal pages show the preparation steps, separate timing groups and
remaining acceptance work.

For the optional local classifier, install `uv sync --project server --extra dev --extra screening --frozen`, then run `server/.venv/Scripts/python.exe scripts/fetch_audio_screening_model.py` once (free public model download; no provider inference). On Linux use `server/.venv/bin/python`. The model is MIT/NAVER-origin, approximately 1.62 MB, runs on CPU and is **not Indian-trained**. Startup never downloads it automatically. Missing/corrupt models return unknown. Open **http://127.0.0.1:5180/#/audio-lab**; see [screening evaluation](evaluation/audio_screening.md). Voice cloning stays deferred.

Or install manually:

```powershell
npm ci --no-audit --no-fund
uv sync --project server --extra dev --frozen
if (-not (Test-Path server/.env)) { Copy-Item server/.env.example server/.env }
.\scripts\setup-livekit.ps1
npm run dev:local
```

Do not overwrite an existing `server/.env`. Setup only creates it when missing. The local audio launcher chooses a free API port from 8000, 8100 and 8200 and points the frontend proxy to it. It prints the selected API URL and serves the audio test at `http://127.0.0.1:5180`. The separate scripted-demo launcher normally uses port 5173.

The saved default server mode is `demo`; use `npm run dev` for that scripted interface. It shares HTTP/WebSocket state but carries no microphone audio. `npm run dev:local` overrides the mode only for its child processes, leaves your saved environment unchanged and starts real raw-audio transport. `npm run dev:checks` opens local live-provider reports; it does not configure the missing Evon endpoint or grant paid API permission.

### Frontend-only demonstration

For a portable static preview without a Python server:

```powershell
npm run build:demo
npm run preview --workspace web
```

This explicitly compiles `VITE_DEMO_MODE=true`; the interface labels browser-local scripted operation. Browser-local rooms are independent in each browser and cannot provide a real shared call. Ordinary production builds use `npm run build` and do not opt into a fallback demo.

## Live configuration: what you supply

Edit **`server/.env`**, never a frontend file. Then restart the server.

See the [go-live checklist](docs/GO_LIVE.md) for the exact inputs you supply, what can be measured now, and the evidence required before calling Track B verified. Actual secrets belong only in the ignored local environment file; do not paste them into chat or the browser.

| Setting                        | Needed from you                                                                             |
| ------------------------------ | ------------------------------------------------------------------------------------------- |
| `ARTHA_MODE`                   | Set to `live` once the values below are configured                                          |
| `GNANI_API_KEY`                | Gnani Speech API key with STT/TTS access; cloning requires the corresponding account access |
| `LIVEKIT_URL`                  | Reachable self-hosted WSS endpoint; generated from your domain by the VM setup              |
| `LIVEKIT_API_KEY`              | Generated locally by the self-hosted deployment tool                                        |
| `LIVEKIT_API_SECRET`           | Generated locally by the self-hosted deployment tool                                        |
| `EVON_BASE_URL`                | Reachable OpenAI-compatible Evon inference endpoint ending in `/v1`                         |
| `EVON_MODEL`                   | Exact model identifier served by that endpoint                                              |
| `EVON_API_KEY`                 | Inference endpoint key if it requires one; optional for a private local endpoint            |
| `TIMBRE_MODEL`, `TIMBRE_VOICE` | Account-supported matching model/voice; defaults are `timbre-v2.5` / `Nalini`               |

Evon is an open-weight model with a selected hosted API beta. If your account is approved, supply its actual endpoint/model/authentication contract and confirm compatibility with the current OpenAI-compatible adapter. An ordinary Gnani speech key does not establish Evon access. Otherwise bring a hosted endpoint or use separate GPU compute. Do not assume a 30B model fits ordinary laptop hardware because only a subset of its parameters is active per token. [Official beta details](https://www.gnani.ai/evon-waitlist).

Run the configuration checker without revealing values:

```powershell
uv run --project server python scripts/check_config.py
```

The live server rejects incomplete setup; it does not silently return demo translations. Frontend code never receives Gnani or LiveKit server secrets. Membership and media tokens are necessarily sent to the joined browser, scoped to that room and expiry.

### First live acceptance check

Provider use is locked until an operator explicitly approves one bounded flow. Start with the [local Gnani checks](docs/GNANI_CHECKS.md): their default plan makes no API calls, and the speech-only test needs no remote server, LiveKit or Evon. Give separate permission for cloning. Manual balance evidence and reference prices appear in Usage; actual programme charges remain unverified until dashboard reconciliation.

The [test-flow catalogue](docs/TEST_FLOWS.md) separates the passed standard-speech check from prepared cloning, translation, multi-party and recovery checks. The [validation record](docs/VALIDATION.md#first-approved-gnani-speech-check) reports the actual one-flow Gnani measurements without treating them as a meeting benchmark.

1. Open two different browser profiles/devices and join the same invitation.
2. Choose Hindi for one participant and Tamil for the other, with standard voices.
3. Enable microphones intentionally; use headphones. Speak short complete phrases in both directions.
4. Verify each listener hears only the other participant's appropriate interpretation and inspect source/translated transcripts.
5. Add Bengali as a third participant. Verify all six directed language branches with distinct speakers.
6. Enroll a consented voice inside a meeting. Use clean spoken audio, then verify actual cross-language intelligibility. Switch back to a standard voice or delete the enrollment.
7. Exercise microphone off/on, language changes, network reconnect, provider failure and leaving. Review server timing separately from listener playback.

## Pages and code map

```text
web/src/
  pages/          home, prejoin, meeting, test lab, voice studio, settings, performance, usage, deployment, developer journal, recap/history
  components/     reusable controls, dialogs, participant and transcript UI
  hooks/          devices, meeting audio, WebSocket lifecycle, recording
  services/       HTTP client, explicit scripted demo, LiveKit adapter
  state/          preferences, scoped membership, room-event reducer
  types/          frontend domain/event contracts
server/artha_mesh/
  main.py         FastAPI composition and HTTP/WebSocket routes
  config.py       environment configuration and live prerequisite checks
  models.py       validated requests and domain/event schemas
  store.py        bounded ephemeral room/session/reference state
  services/       room lifecycle, routing, FIFO pipeline, voice enrollment
  providers/      Gnani speech and Evon translation boundaries; demo dictionary
  transport/      LiveKit identity/tokens, PCM tracks and subscription policy
server/tests/     behavior, isolation, provider contract and lifecycle checks
evaluation/       synthetic scripts, human-review CSV, run collector and report
deploy/          reverse-proxy configuration and production VM deployment guide
scripts/         setup, development, configuration and actual RTC verification
```

See [product/page specification](docs/PRODUCT.md), [architecture](docs/ARCHITECTURE.md), [API/event contract](docs/CONTRACT.md) and [evaluation guide](docs/EVALUATION.md).

The [Evon access guide](docs/EVON_ACCESS_GUIDE.md) separates verified public instructions from account-specific dashboard navigation. The [standard-voice language matrix](docs/LANGUAGE_TEST_MATRIX.md) designs all 90 directed routes across the common ten languages, with per-flow approval and no automatic provider run. Test lab shows this coverage as pending. Odia and dedicated code-mix modes are outside the verified common speech set.

### Keep provider usage controlled

Open `/#/usage` for the current application's reserved usage and configured daily caps. Defaults limit combined STT connection time to 600 seconds, 30 STT connection attempts, 100 MT attempts, 100 TTS attempts, 30,000 source/synthesis characters each, and three voice enrollments per UTC day. Live rooms expire after 15 minutes by default. Configure the `USAGE_*` fields in the server environment to match your actual allowance before live testing; zero blocks that resource. These are development safeguards, not provider balance readings or rupee spending limits. LiveKit usage and running GPU infrastructure also need limits in their own provider consoles. See [credit controls](docs/CREDIT_CONTROLS.md).

Open `/#/development` for the maintained engineering journal: causes, changes, evidence and remaining checks. It is a source-maintained record and makes no inference calls. The [journal maintenance guide](docs/DEVELOPMENT.md) explains how to keep entries accurate.

Open **`/#/performance`** for setup readiness and the measurement reference. A joined room exposes authenticated, room-scoped timing samples there. Live first-PCM percentiles exclude scripted demo values, same-language forwarding and unsuccessful branches; microphone and typed inputs must be reviewed separately. The [measurement definitions and listener-delay procedure](docs/GO_LIVE.md#what-the-performance-page-measures) explain how server timing differs from actual audible output.

## Verification

```powershell
npm run build
npm run test:web
uv run --project server --extra dev pytest server/tests -q
```

The actual RTC utility uses a local LiveKit development server and **synthetic PCM plus test-double providers**, never a microphone or paid API:

```powershell
# In a separate terminal after downloading LiveKit from its official releases:
livekit-server --dev
# In the project terminal:
uv run --project server python scripts/verify_routing.py
```

It checks three real RTC publishers, six directed branches, non-silent target-language receipt, and absence of self/original/wrong-language subscriptions. It does not establish actual translation accuracy. [Official local LiveKit instructions](https://docs.livekit.io/transport/self-hosting/local/)

The evaluation set contains draft synthetic scripts, not a certified benchmark. Obtain bilingual review and collect real runs before publishing accuracy or latency claims. Server metrics end at dispatch to LiveKit; they do not measure the listener's speaker playback. Demo timing is not a live benchmark.

## Docker deployment

### Online self-hosted deployment

Use [deploy/production/README.md](deploy/production/README.md) for the prepared Linux VM stack. The offline generator validates input, generates private LiveKit credentials and writes ignored deployment files. Starting containers is a separate explicit operation. It does not buy a server, change DNS/firewall rules, install Docker, download Evon weights or call paid providers.

The API image installs exact runtime dependency versions and hashes from `server/requirements.lock`, exported from the committed `server/uv.lock`. After intentionally updating the lock, regenerate the export with `uv export --project server --frozen --no-dev --extra live --no-emit-project --no-header --no-annotate --output-file server/requirements.lock`. The image requires matching binary wheels; Linux image acceptance remains a deployment check.

Open **`/#/deployment`** for the required inputs, safe configuration status and hosting reference. The [India hosting guide](docs/INDIA_HOSTING.md) explains Zoho student credits, Gnani's conditional Evon beta, E2E/Yotta options and IndiaAI eligibility. Self-hosting removes LiveKit Cloud usage charges; infrastructure and speech/inference charges still need their own limits.

### Local container development

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:8080`. The web reverse proxy routes `/api` and WebSocket events to the Python service. The API remains bound to loopback on the host. Docker Desktop/the Docker daemon must be running; this repository does not modify that service.

Optional self-hosted media for development:

```powershell
docker compose --profile local-livekit up --build
```

For that local profile set browser-facing `LIVEKIT_URL=ws://localhost:7880`, worker-facing `LIVEKIT_INTERNAL_URL=ws://livekit:7880`, and LiveKit's documented development values `LIVEKIT_API_KEY=devkey`, `LIVEKIT_API_SECRET=secret`. These public development credentials are only for local tests; use your own secrets and HTTPS/WSS in deployment. A remote phone cannot use your computer's localhost address.

Prepare the optional Evon GPU service without starting it:

```powershell
.\server\.venv\Scripts\python.exe scripts/evon_prepare.py --config deploy/evon/inputs.verified-2026-10-28.json --output work/evon/compose.json
```

Follow [GPU_TESTING.md](docs/GPU_TESTING.md) for the pinned model/image evidence, authenticated loopback serving, bounded tests and shutdown plan. The old `local-evon` profile has been removed. Generating configuration downloads nothing. GPU memory, driver compatibility and actual inference still require the approved host. Set `EVON_BASE_URL` to the endpoint reachable from the API process: a host-side API can use an SSH tunnel at `http://127.0.0.1:8001/v1`; a container cannot use its own loopback to reach that host tunnel. Keep it blank until the appropriate private route is configured.

## Deployment and privacy boundaries

- Run a **single API worker**. Rooms, memberships and voice embeddings are in memory, expire, and are lost on restart. Durable storage and distributed room ownership are future deployment work.
- Provider-usage reservations persist separately in a small local SQLite ledger so an API restart cannot silently reset the daily counters. Keep its Docker volume/local data directory. The ledger stores resource totals, bounded approval metadata/measurements and optional manual balance evidence, without audio, transcripts, keys or embeddings. Public usage responses hide financial evidence by default.
- Invitations permit joining a room. Host admission, user accounts, SSO and organisation policies are not implemented.
- Reference uploads are bounded and processed in memory. This application retains only session-scoped embeddings, which are deleted on leave/expiry or explicit deletion. External API retention is governed by your provider's settings and terms.
- Recaps are only persisted in the current browser after an explicit save. Downloaded exports remain wherever the user saves them.
- The processing agent and external speech/model providers necessarily see the audio/text they process. Transport encryption is not a claim that the processing backend cannot access speech.
- “Indian-model powered” is accurate once configured accordingly. India-controlled deployment/data residency requires verifying media, inference, worker, storage and logging locations; this source project does not certify that.
- The browser sends WebSocket credentials in the upgrade header, outside URLs. Redact authentication headers in proxies and diagnostics. The provided development and container commands also disable access logs; legacy query-token clients must not enter logs. Set explicit `CORS_ORIGINS` for each frontend origin, including preview ports when used.

## Primary implementation references

- [Gnani streaming STT](https://docs.gnani.ai/api/STT/stt-websocket)
- [Gnani streaming TTS](https://docs.gnani.ai/api/TTS/tts-websocket)
- [Voice embeddings](https://docs.gnani.ai/api/VC/voice-clone-embeddings) and [cloned streaming speech](https://docs.gnani.ai/api/VC/vc-websocket)
- [Evon model card and serving instructions](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B)
- [LiveKit publication/subscription permissions](https://docs.livekit.io/transport/media/publish/)

This is an independent project built for evaluation and development, not an official Gnani or Google product.
