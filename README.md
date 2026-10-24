# Artha-Mesh

**Conversations without language barriers.** An Indic audio meeting application implementing Track B: streaming speech recognition, translation, speech synthesis, bidirectional and multi-party routing, and optional consent-based voice cloning.

The application separates its React pages, reusable UI, hooks, domain state, API client and LiveKit media adapter from the Python API, room/session services, translation pipeline, provider adapters and RTC transport. No deepfake detector or Track A verdicts are included.

## What is implemented

- Home workspace, room creation/invitation, prejoin language and device selection.
- Meeting stage with participant cards, microphone/speaker controls, captions, transcript/source views, language changes, room details, reconnect actions and explicit leave.
- Hindi, Tamil, Bengali and English source/listening languages.
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

**Implementation is not vendor validation.** Real Gnani/Evon speech quality, account permissions, clone intelligibility and receiver playback latency must be verified after configuring working credentials and compute. Demo participants and translations are scripted. Configured settings are not proof of a successful provider connection.

## Run locally

Requirements: Node.js 22+, Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). Use a current Node 22 release for the installed dependency tree. A microphone requires localhost or HTTPS.

From the project directory in PowerShell:

```powershell
.\scripts\setup.ps1
npm run dev
```

Or install manually:

```powershell
npm install
uv sync --project server --extra dev
Copy-Item server/.env.example server/.env
npm run dev
```

Do not overwrite an existing `server/.env`. The setup script only creates it when missing. The development launcher chooses a free API port from 8000, 8100 and 8200 and points the frontend proxy to it. It prints the selected API URL; Vite prints the frontend URL, normally `http://127.0.0.1:5173`.

The default server mode is `demo`. Create a room, choose a name/language, check the processing-consent box, join, and start the scripted example. Backend demo rooms share HTTP/WebSocket state between browsers but do not run speech recognition or synthesize translated audio.

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
| `LIVEKIT_URL`                  | Reachable self-hosted WSS endpoint; generated from your domain by the VM setup             |
| `LIVEKIT_API_KEY`              | Generated locally by the self-hosted deployment tool                                       |
| `LIVEKIT_API_SECRET`           | Generated locally by the self-hosted deployment tool                                       |
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
  pages/          home, prejoin, meeting, voice studio, settings, performance, usage, deployment, developer journal, recap/history
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

Optional Evon GPU service:

```powershell
docker compose --profile local-evon up --build
```

Requires a compatible NVIDIA GPU/runtime, sufficient model memory, model access accepted by you, and `HF_TOKEN` when required for the download. The model is large; this profile is not started by default. The root `.env.example` points the containerized API to `http://evon:8000/v1`. For a separately run local API, use the exposed `http://127.0.0.1:8001/v1` instead. Validate GPU capacity and serving compatibility before a live demo.

## Deployment and privacy boundaries

- Run a **single API worker**. Rooms, memberships and voice embeddings are in memory, expire, and are lost on restart. Durable storage and distributed room ownership are future deployment work.
- Provider-usage reservations persist separately in a small local SQLite ledger so an API restart cannot silently reset the daily counters. Keep its Docker volume/local data directory. The ledger stores only dates, resource names and reserved unit totals.
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
