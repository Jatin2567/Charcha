# Prepared test flows

Inspecting plans, reports and UI makes no inference calls. Each actual provider flow needs a separate operator approval; do not run the entire list automatically. Public hosting is unnecessary for the first two local checks.

Use `npm run dev:checks` after setup to open the local reporting workspace, then visit `/#/usage`. The published static preview is a UI/reference view; your private account ledger remains local.

| Flow | Current evidence | Inputs | Pass condition |
| --- | --- | --- | --- |
| **1. Gnani speech round trip** | Passed once with the actual Gnani account on 24 October 2026 | One explicit grant; configured speech key | One short Hindi TTS result is nonempty PCM; one STT connection returns the intended phrase; units/timings are recorded and grant closes |
| **2. Consented voice cloning** | Runner and mocked contracts tested; real check pending | Own clean 5–30-second PCM WAV, explicit cloning consent and separate grant | One embedding request and one cloned synthesis complete; speaker reviews similarity; no embedding enters the report |
| **3. Hindi↔Tamil interpretation** | Pipeline and local synthetic RTC tested; real-provider meeting pending | Working Evon endpoint/model/auth contract, local/self-hosted LiveKit, two consenting speakers and one bounded meeting grant | Each hears only the other's target-language output; meaning, quantities and negation are confirmed; room timings exported |
| **4. Three-speaker routing** | Six directed synthetic RTC branches passed; real speech pending | Add Bengali speaker, appropriate live grant | All six directed language routes, no self-echo, no original/translated double playback and correct same-language handling |
| **5. Recovery and limits** | Automated lifecycle and budget tests passed | Local test doubles for destructive/failure cases; separate approval for any real-provider repetition | Mute, disconnect, expiry, quota denial, cancellation and replacement grants do not create stale output or unapproved paid work |

## Speech check plan

```powershell
.\server\.venv\Scripts\python.exe scripts/check_gnani.py --plan
```

The fixed phrase is “नमस्ते भारत।”. Its exact 60-second grant permits one TTS attempt, 12 synthesis characters, one STT connection and nine conservatively reserved connected seconds. STT wall time is capped at eight seconds. All MT/enrollment budgets are zero; no retries occur. The single approved real run used four reserved STT seconds and produced the same transcript. See [VALIDATION.md](VALIDATION.md) for actual measurements.

## Voice-clone check plan

```powershell
.\server\.venv\Scripts\python.exe scripts/check_gnani.py --plan --purpose voice_clone_check
```

Its exact 60-second grant permits one enrollment and one 12-character cloned synthesis attempt. It has no STT or MT allowance. Run only after the reference is checked and the human approves the separate flow. Supply the existing flow UUID, `--reference <own-reference.wav>` and `--consent-own-voice`. No reference is fabricated, and the script never records a microphone automatically.

For checks 3–4, use the application and [GO_LIVE.md](GO_LIVE.md). Grant only the intended short test window and resource budgets rather than using the full daily caps. Stop microphones between flows and deliberately restart them after any new approval. Use standard voices first; cloned interpretation is an additional human-review case.

## API usage reference

Gnani's [REST STT instructions](https://docs.gnani.ai/api/STT/speech-to-text) describe multipart `audio_file` and `language_code` for short recordings, with `X-API-Key-ID` authentication. They recommend [WebSocket STT](https://docs.gnani.ai/api/STT/stt-websocket) for live audio; the application uses the corresponding upgrade headers and paced PCM frames. REST's documented response includes the transcript, request ID and timestamp, without an actual billed-credit field. The project's direct adapters retain explicit retry and approval control instead of introducing an SDK's automatic retries.

Reports keep measured server boundaries separate from actual listener playback. The Usage page records per-flow reservations and safe measurements; Performance records live room branches. Draft evaluation scripts require bilingual review before any benchmark claim.
