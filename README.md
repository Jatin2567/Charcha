# Charcha

**Multilingual meetings with shared understanding.** Charcha combines spoken interpretation, personal voices, original/translated captions, participant corrections and a bilingual conversation record. It is an independent project built using Gnani AI technology.

[Hosted app](https://charcha-234398803946.asia-south2.run.app/) · [Submission package](docs/SUBMISSION.md) · [Live rehearsal](docs/LIVE_SUBMISSION_REHEARSAL.md) · [Operating guide](docs/ON_DEMAND_MEETINGS.md)

## Current stage — 9 November 2026

The current submission film is `work/demo-video/story-v11/Charcha-60-second-final.mp4` (local, ignored by Git): 60 seconds of recorded Hindi→English provider audio, actual UI replay, a typed correction, fresh acknowledgement and a bilingual recap. Fictional illustrations and synthetic test speech are disclosed. It is not a fresh live latency benchmark. See the [final submission package](docs/SUBMISSION.md); public video/social links are pending.

The deployed `refresh-connection-20261109` release passed health, served-bundle and backend source checks on 9 November. Protected account/admin endpoints rejected anonymous access. These checks did not start inference or establish the quality of a new conversation.

The intended use is everyday coordination between people who do not share a fluent language. Listeners hear an interpretation, inspect both texts, request clarification and confirm understanding of the latest version. Corrections preserve earlier versions and require fresh acknowledgements. These actions support human review; they do not automatically prove translation accuracy or agreement.

## Implemented experience

- A designated host signs in, creates a meeting, shares an invitation and admits or denies signed-in guests. Administrator access uses separate credentials and authenticator verification.
- Browser audio/video, device controls, captions, transcripts, language selection, reconnect guidance and departure use LiveKit WebRTC.
- Refresh/reconnect requests a fresh short-lived media credential for the same admitted seat. It preserves voice setup and starts with microphone/camera off. Expired memberships, explicit leave and sign-out still require valid re-entry.
- Gnani Prisma streams recognition, hosted Evon translates, and Gnani synthesis delivers target-language speech. Hosted interpreted meetings require consented own-voice enrollment before speaking. Listeners can join without enrolling.
- Ten configurable languages: Hindi, Tamil, Bengali, English, Telugu, Kannada, Malayalam, Marathi, Gujarati and Punjabi. Configuration coverage is broader than measured live quality.
- Translation branches are shared by target language, with ordered playback, bounded preparation overlap and visible handling of expired or failed turns. Same-language listeners receive original audio through the agent.
- Each turn records eligible listeners and their acknowledgements. PDF printing, WhatsApp preview/copy, text and JSON exports preserve corrections and missing information. Sharing is user-initiated.
- Performance reports distinguish server stages, queueing, browser observations, failures and missing data. Account-scoped performance history persists on the server. Saved conversation recaps are browser-local and separate from that history.
- The GPU is shared across occupied interpreted meetings and can scale down after the last meeting ends. Connecting meeting audio can start GPU preparation even while muted. Startup and warm idle time consume credits.
- VoiceShield is experimental incoming-audio screening with a local Audio lab. Monitoring reports signals while speech continues. It is not validated fraud prevention or an identity check.

## Evidence and limits

| Evidence | Recorded result | Scope |
| --- | --- | --- |
| Final local verification, 9 November | 1,468 backend tests passed, one skipped; 322 frontend tests and seven conference-runtime checks passed; production build passed. | Isolated local tests, not a fresh provider conversation. Read-only hosted checks returned 200 for the page/health and 401 for anonymous performance history. Logs: `work/submission-final/`. |
| Five-language stage, 31 October | Nine of ten attempted routes delivered audio with real providers across Hindi, Tamil, Bengali, Telugu and Marathi. One failed before provider use. | Programmatic RTC receivers, standard voices, meaning review pending; a number-recognition error is documented. [Route evidence](web/src/data/fiveLanguageStageResults.json). |
| Live meeting, 6 November | 24 completed cloned-synthesis branches: 16 English→Hindi and eight Hindi→English; 23 audio inputs and one typed input. | Successful execution is not a similarity or translation-accuracy score. |
| Same meeting, before queue fix | Server first-audio p50 5.66 s and p95 21.99 s. | Historical partial server timings mixing recorded input kinds. STT timing and listener observations absent. Not current end-to-end latency. |
| Queue/browser instrumentation, 7 November | Offline checks exercised preparation overlap, ordered RTC delivery, browser onset and saving. | Fake providers/generated audio; no fresh real-provider speed claim. |
| Verification, 8 November | 313 frontend tests passed; production bundle built. Focused backend runs recorded 35 and 42 passes. | Backend runs overlap; do not add them into a full-suite total. |
| Refresh correction, 9 November | 322 frontend tests and 60 focused backend tests passed; build passed. Isolated Chrome reloaded an expired cached token and reconnected real local RTC with the same seat. | Injected media-token expiry, local original-audio transport, no providers. Microphone/camera stayed off; replay after leaving was denied. Not a live translation test. |
| Public-human screening pilot | 50 recordings: 24 allowed, 14 false alarms, 12 unknown. | No synthetic class, so AI detection rate is unknown. [Study](docs/PUBLIC_HUMAN_SCREENING.md). |

Historical standard-voice experiments also recorded a 1.56 s median server stage. It excludes the complete speech-to-listener path and must not headline current latency. The [journal](web/src/data/developerJournal.ts) records dated evidence. Operator receipts are in ignored `work/`; publish only reviewed, non-sensitive summaries.

VoiceShield needs a 4,037.5 ms audio window plus computation. Jitter/shimmer cannot prove whether a voice is human. Voice enrollment supports synthesis, not identity verification. A recap SHA-256 value is a source-record fingerprint, not a digital signature, immutable ledger or legal proof of agreement.

## Run without speech or GPU credits

Requirements: Node.js 22+, Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). Microphones require localhost or trusted HTTPS.

```powershell
.\scripts\setup.ps1
.\scripts\setup-livekit.ps1
npm run dev:local
```

Open `http://127.0.0.1:5180/#/tests`. This launcher uses original audio and clears speech-provider credentials for its processes. Use independent Chrome profiles and headphones to test transport. This does not test translation/cloning. Stop the owned stack with Ctrl+C.

`npm run dev` opens the explicitly scripted interface (default port 5173). Its example turns and metrics are not live evidence. `npm run build:demo` builds a labelled static preview with browser-local rooms.

`npm run check:conference` checks local dependencies/configuration without starting services. The optional `npm run dev:shield` uses the installed CPU screening model with original audio. See [screening setup](evaluation/audio_screening.md).

## Live interpretation

Read the [operating guide](docs/ON_DEMAND_MEETINGS.md) and [rehearsal](docs/LIVE_SUBMISSION_REHEARSAL.md). The hosted application uses owner-funded meetings without per-turn operator approval. **That product setting does not authorize a new assistant-run paid test.** Obtain explicit approval before connecting interpreted audio, enrolling voices or starting provider work.

`npm run dev:live` is provider-enabled. Depending on configuration, a meeting can trigger remote compute and speech use. Older bounded-flow scripts have their own approval mechanisms and are not the current hosted workflow.

Keep secrets in private server configuration, never frontend code, screenshots or public exports. Main settings include:

| Setting | Purpose |
| --- | --- |
| `CHARCHA_MODE` | `live` for interpretation; `transport` for original audio |
| `GNANI_API_KEY` | Speech and enabled cloning services |
| `LIVEKIT_URL`, `LIVEKIT_INTERNAL_URL` | Browser-facing and server-facing media endpoints |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Private media-server credentials |
| `EVON_BASE_URL`, `EVON_MODEL`, `EVON_API_KEY` | Inference endpoint, served model and authentication |
| Voice, identity and serverless settings | See `server/.env.example` and deployment guides; values stay private |

A Gnani speech key does not supply an Evon GPU endpoint. This deployment hosts Evon on Modal. Usage tracks service units; the owner currently monitors Gnani billing. Do not substitute standard-TTS prices for unknown cloning prices.

## Architecture and deployment

```text
Browser microphones / cameras → LiveKit SFU
Python room agent → Prisma STT → Evon translation → Gnani cloned synthesis
                  → ordered target-language audio + bilingual captions
Incoming microphone audio → optional experimental CPU VoiceShield
Room events → versioned corrections / acknowledgements / recap
Timing events → account-scoped persistent performance reports
```

React pages, components, hooks, state and adapters are in `web/src/`. FastAPI routes, room services, provider adapters and media transport are in `server/charcha/`. Tests are in `web/src/` and `server/tests/`; evaluation cases are in `evaluation/`.

The app, media and Keycloak identity service are hosted in GCP Delhi. Modal uses the configured Asia allocation; the entire processing chain is **not verified India-only**. LiveKit is an SFU, not a peer-to-peer mesh. SIP/PSTN integration is not deployed. No configured participant cap does not imply unlimited capacity.

Use one API worker. Active rooms, memberships and embeddings are memory-resident and lost on restart. Account settings, usage and performance history persist; preserve volumes. Browser-saved conversation recaps are separate. Embeddings are deleted on leave/expiry or deletion; external provider retention follows provider terms. Processing services can access the speech/text they handle despite transport encryption.

[Architecture](docs/ARCHITECTURE.md) · [Deployment files](deploy/gcp/) · [Operations](docs/ON_DEMAND_MEETINGS.md) · [Evaluation](docs/EVALUATION.md)

Earlier runbooks describe historical Auth0, standard-voice and bounded-approval configurations. Current operating instructions and dated evidence take precedence. Historical resource IDs and the checkout path retain `artha` names where changing them would break existing resources.

## Verification

```powershell
npm run build
npm run test:web
uv run --project server --extra dev pytest server/tests -q
```

These checks use isolated fixtures and do not establish provider quality. Record revision, command, date, pass/skip/failure counts and scope before quoting a total. The supplied 1,764-test claim is not adopted as the current full-suite result without its matching receipt.

Final acceptance follows the [three-pair rehearsal](docs/LIVE_SUBMISSION_REHEARSAL.md). Keep failed and unmeasured attempts in the record. Fluent listeners, not caption checks alone, establish whether intended meaning reached them.

## Primary references

- [Gnani challenge](https://www.gnani.ai/internship)
- [Prisma recognition](https://docs.gnani.ai/api/STT/stt-websocket)
- [Speech synthesis](https://docs.gnani.ai/api/TTS/tts-websocket)
- [Voice embeddings](https://docs.gnani.ai/api/VC/voice-clone-embeddings) and [cloned synthesis](https://docs.gnani.ai/api/VC/vc-websocket)
- [Evon model](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B)

Charcha is not an official Gnani, Google or Modal product. Demonstrate actual behavior and distinguish measured results from goals.
