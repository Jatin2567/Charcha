# Charcha · चर्चा

**Speak in your language. Review the change. Keep one shared plan.**

Charcha combines multilingual audio/video meetings with spoken interpretation, original/translated captions, versioned corrections, fresh listener acknowledgements and a bilingual recap. It is an independent project built using Gnani AI.

[One-page pitch](docs/Charcha-one-page-pitch.pdf) · [2:40 build film](docs/media/Charcha-2m40-multilingual-build.mp4) · [60-second multilingual story](docs/media/Charcha-60s-multilingual-voices.mp4) · [Hosted app](https://charcha-234398803946.asia-south2.run.app/) · [Submission guide](docs/SUBMISSION.md)

[Entrant's LinkedIn post](https://lnkd.in/p/g9n3W6Cj) · Final pitch refreshed on 10 November with current application checks and separately dated provider timings.

**Evaluating the portal?** The [reviewer setup guide](docs/REVIEWER_GUIDE.md) explains authenticated invitations, creating and admitting participants to your own meetings, shared or reviewer-supplied Gnani/Evon resources, preparing translation before joining, and account-scoped activity/readiness reports. Release `reviewer-reporting-20261110` was deployed and checked on 10 November. Reviewers still need a private invitation; no invitation or live provider test is implied by this deployment.

**Source revision, 10 November 2026:** this revision includes the refreshed films and pitch, Sathvika's approved feedback, reviewer access and pre-meeting translation preparation. Hosted health, served components and access restrictions were checked separately from local tests. Public-video/social links and challenge submission remain separate steps. See the [release record](docs/SUBMISSION_RELEASE_NOTES.md).

## The problem, in one conversation

A workshop organiser says, **“Bring twelve blue files to room three at four.”** The room changes to four. Hearing the first translation is no longer enough: each participant needs the updated instruction and a visible way to acknowledge it.

Charcha preserves the earlier message, translates the correction, separates old and new acknowledgements, and retains both versions in the recap. Teams, students and community organisers can use this workflow for changed times, quantities or locations. The latest film follows fictional Asha, Ravi and Meher through Hindi, Telugu and Punjabi, using actual interface screens from a scripted three-account rehearsal and prepared speech readings.

## What the application does

- **Multilingual meetings:** LiveKit browser audio/video with ten language options: Hindi, Tamil, Bengali, English, Telugu, Kannada, Malayalam, Marathi, Gujarati and Punjabi.
- **Gnani interpretation:** Prisma recognition → hosted Evon translation → Gnani speech synthesis and consented own-voice cloning. Live interpretation needs configured credentials and available compute.
- **Reviewable messages:** Original/translated captions, number and selected-negation highlighting, versioned corrections and acknowledgements per eligible listener. Acknowledgement records understanding, not contractual agreement or automatic accuracy verification.
- **Useful recaps:** PDF printing, WhatsApp preview/copy, text and JSON export. Sharing is user-initiated. The SHA-256 fingerprint identifies the recorded payload; it is not a signature or immutable ledger.
- **Meeting controls:** Host sign-in and admission, separate administrator authenticator verification, device controls and refresh/reconnect recovery for an admitted seat.
- **Inspectable performance:** Queue and stage measurements, browser observations and account-scoped saved performance reports. Missing measurements remain explicit.
- **Efficient routing:** Shared translation/synthesis per target language, ordered playback and bounded preparation concurrency. Modal compute follows occupied interpreted meetings and scales down afterward; startup and idle time still consume compute.
- **VoiceShield:** Optional experimental source-audio screening, visible results and a local Audio lab. Model scores are separate from DSP diagnostics and do not establish identity or validated fraud prevention.

## Recorded evidence

| Evidence | Result | Measurement boundary |
| --- | --- | --- |
| Reviewer reporting release checks, 10 Nov 2026 | **1,579 backend tests passed, one skipped; 335 frontend tests across 47 files; seven runtime checks; build passed** | Local checks with provider responses mocked. Eight focused reporting tests also passed, overlapping the full suite; counts are not additive. Desktop/mobile scoped-report walkthrough passed against the local API without provider calls |
| Hosted reporting release checks, 10 Nov 2026 | Health 200; reviewer/prejoin/usage/performance components present; protected anonymous requests denied; all 43 deployed source hashes matched with no missing/extra files | Health/access checked at 16:31:03 UTC; full source match at 16:31:12 UTC. No authenticated live provider flow or provider calls |
| Local checks, 9 Nov 2026 | 1,468 backend tests passed, one skipped; 322 frontend tests and seven runtime checks passed; build passed | Isolated application checks, not a new provider-quality test |
| Two demo cases, 9 Nov 2026 | **3.94 s** original turn; **4.23 s** typed correction | Translation start → first decoded synthesis audio; excludes STT, meeting transport and listener playback |
| Five-language stage, 31 Oct 2026 | Nine of ten attempted routes delivered across Hindi, Tamil, Bengali, Telugu and Marathi | One failed during local setup before provider use; delivery is not a meaning-accuracy score |
| Media-token recovery | Same admitted seat reconnects after injected token expiry in isolated local Chrome | Original-audio transport; microphone/camera remain off after reload |

The latest films use fictional illustrations, a scripted three-account UI rehearsal and prepared stock-voice readings, with quiet locally synthesized background music. They are edited workflow demonstrations, not newly recorded live three-device interpretation or cloned-voice tests. The build film separately explains the dated provider measurements above. Ten configurable languages do not imply tested quality for every pair. VoiceShield has no established detection-accuracy figure. See [evaluation](docs/EVALUATION.md), [route evidence](web/src/data/fiveLanguageStageResults.json) and [submission evidence](docs/SUBMISSION.md).

## Architecture

```text
Browsers ←→ LiveKit SFU ←→ Python room agent
                           ├─ Prisma STT → Evon MT → Gnani synthesis
                           │               └─ shared target-language branches
                           ├─ optional CPU audio screening
                           └─ ordered audio, captions, corrections and timing events

React / TypeScript UI ←→ FastAPI services ←→ identity / room / report persistence
```

Pages, hooks, services and media adapters are separated under `web/src/`. Provider adapters, routing, screening, membership and persistence live under `server/charcha/`. Tests are in `web/src/`, `server/tests/` and `evaluation/`.

The app/media/identity deployment uses GCP Delhi; Evon uses the configured Modal allocation. The full processing chain is not verified India-only. LiveKit is an SFU, not a peer-to-peer mesh. Active rooms and embeddings are memory-resident: use one API worker and consult the [operating guide](docs/ON_DEMAND_MEETINGS.md). Server performance history and browser-saved recaps have distinct persistence scopes.

## Run locally without provider credits

Requirements: Node.js 22+, Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/) and Windows PowerShell for these scripts.

```powershell
git clone https://github.com/Jatin2567/Charcha.git
cd Charcha
.\scripts\setup.ps1
.\scripts\setup-livekit.ps1
npm run check:conference
npm run dev:local
```

Open `http://127.0.0.1:5180/#/tests`. This starts **original-audio transport**, with provider interpretation, cloning and screening disabled. Use separate browser profiles and headphones. Setup downloads dependencies and pinned LiveKit; it does not call speech/GPU providers.

Keep live settings in private `server/.env`; consult `server/.env.example` and deployment guides. A Gnani speech key alone does not provision Evon compute. Microphones require localhost or trusted HTTPS.

## Checks and project record

```powershell
npm run test:conference-runtime
npm run test:web
npm run test:server
npm run build
```

Tests use fixtures and isolated services. Keep date, scope and command alongside results; test counts do not establish human translation quality.

[Architecture](docs/ARCHITECTURE.md) · [Evaluation](docs/EVALUATION.md) · [Award evidence map](docs/AWARD_POSITIONING.md) · [Publication record](docs/SUBMISSION_RELEASE_NOTES.md) · [Commit history](https://github.com/Jatin2567/Charcha/commits/main/)

Charcha is not an official Gnani, Google or Modal product. Development and demo production used AI assistance and established libraries. Awards and internships depend on Gnani's review and [programme rules](https://www.gnani.ai/internship).
