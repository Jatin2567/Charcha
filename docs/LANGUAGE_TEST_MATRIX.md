# Standard-voice language flow and acceptance matrix

**Current conferencing scope:** all ten configured languages can use the normal
call flow with adequate provider configuration and operator-approved budgets.
Latency optimization is deferred and does not block joining or routing. See
[LIVE_CONFERENCING.md](LIVE_CONFERENCING.md).

The optional latency-research workflow below optimizes **Hindi→Tamil first**, accepts the reverse direction only after the first physical latency gate, and opens the other **88 directed pairs for test review only after both gates pass**. It is a separate research planner, not a production call gate. Every live flow still needs a fresh bounded approval. Planning and a passing gate grant no permission and make no API request.

The current offline entry point is `scripts/plan_latency_language_workflow.py`. It reads the exact ten-language stock catalog from `server/charcha/voice_catalog.py`, includes 90 directed cross-language pairs and ten optional same-language forwarding checks, and provides 40 ordinary-conversation drafts in `evaluation/language_latency_cases.json`. Existing paid Hindi/Tamil reports remain separate and unchanged. They do not satisfy a physical speech-end-to-listener gate.

## Documented common language set

The [Prisma realtime table](https://docs.gnani.ai/api/STT/stt-websocket#supported-languages), [Evon model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B) and [Timbre stock-voice catalog](https://docs.gnani.ai/api/TTS/available-voices) overlap on the following set. These voice names belong to **`timbre-v2.5`**; model catalogs are not interchangeable.

| Language  | Code | Provider locale | Planned standard voice |
| --------- | ---- | --------------- | ---------------------- |
| Hindi     | `hi` | `hi-IN`         | Nalini                 |
| Tamil     | `ta` | `ta-IN`         | Trisha                 |
| Bengali   | `bn` | `bn-IN`         | Kirra                  |
| English   | `en` | `en-IN`         | Pranav                 |
| Telugu    | `te` | `te-IN`         | Suhana                 |
| Kannada   | `kn` | `kn-IN`         | Saanvi                 |
| Malayalam | `ml` | `ml-IN`         | Reshma                 |
| Marathi   | `mr` | `mr-IN`         | Zahira                 |
| Gujarati  | `gu` | `gu-IN`         | Falak                  |
| Punjabi   | `pa` | `pa-IN`         | Mehuli                 |

Odia appears in Evon's eleven-language list but is absent from the documented realtime STT/TTS intersection. Do not offer a full Odia speech path on that evidence. Dedicated Hinglish, Tanglish and Benglish language codes and automatic detection are separate future capability checks; mixed identifiers inside a selected language are draft review cases, not a broad code-mixing accuracy claim.

The common-ten design contains **90 directed pairs** (`10 × 9`). The ten include English; this is not ten Indian languages plus English. A pair uses two independent sessions. A dropdown, a documented catalog or a successful local mock does not establish account entitlement, meaning preservation or physical listening quality for that language. The planner leaves each provider's live language acceptance, fluent review and device acceptance pending. Odia has no full speech route in the current stock catalog.

## One source, the right recipients

```text
Microphone PCM → one source STT stream → final source transcript
  → one MT job per distinct different listening language
  → one stock TTS job per such target language
  → agent track permitted only to that target-language audience

Same-language microphone listeners → forwarded original source track
Source speaker → never receives their own output
```

STT is needed only while the source is unmuted and has a different-language listener. A persistent source STT connection can produce several utterances; it is not opened once for every recipient. Do not multiply STT by audience size.

For a Hindi speaker with two Tamil listeners, one Bengali listener and one Hindi listener, use **one STT stream, two MT jobs and two TTS jobs per utterance**. Both Tamil listeners share the Tamil synthesis; the Hindi listener receives the original audio. A Hindi-only audience needs no STT/MT/TTS for microphone forwarding. Typed same-language fallback can synthesize speech and is outside this cross-language matrix.

A track waits for its first subscriber before initial delivery, but that does not prove every listener in a shared-language group is ready. Verify every recipient separately at the later multi-party gate. Preserve each source speaker's FIFO, recheck membership and routing after waits, clear stale work on mute/leave, and show errors rather than replacing a failure with a scripted translation.

## Acceptance order

1. Prepare and separately approve a bounded **Hindi→Tamil** optimization flow using standard voices. Keep deepfake screening off and voice cloning deferred.
2. Collect at least **ten warm attempts**, recording every failure and timeout. All ten must complete. Each successful source/target meaning and each timing annotation must be accepted by a fluent reviewer/operator before setting the review flags.
3. Require the physical latency gate below. A pass makes **Tamil→Hindi eligible for a new test approval**; it does not start that test.
4. Apply the same physical gate independently to Tamil→Hindi. Only after both directions pass are the remaining 88 pairs eligible for individually approved test flows.
5. Select small, explicit subsets of the four draft categories per source language. Review source drafts before treating their English meaning as a reference, then review the actual STT and target output. The map of 90 routes is not an authorization to run 90 or 360 provider requests.
6. Repeat accepted two-person checks on the second device and intended HTTPS/WSS deployment. Later test three-party fan-out, shared targets, overlap, language changes, mute, leave, expiry and reconnect.
7. Voice cloning remains a later, separately consented stage.

## Physical speech-end latency gate

The accepted boundary is **source speech end → first listener output**, measured within the **same continuous recording sample clock**. Use observations from `scripts/measure_speech_end_playback.py` with `record_type: speech_end_playback_observation`, `clock: single_recording_sample_index` and `boundary: source_speech_end_to_listener_output`.

Eligible capture kinds are `acoustic_single_channel`, `acoustic_two_channel` and `electrical_loopback_two_channel`. A single phone can record both the source voice and listener output in one mono PCM16 WAV. This shares a sample clock but offers less voice isolation: use a quiet room and clearly distinguishable turns, then review the waveform and listening annotations manually. The analyzer records both channel indices as zero for this capture kind. See the [phone capture workflow](SPEECH_END_LATENCY.md).

Require `provider_kind: live`, `capture_attested: true`, `annotations_reviewed: true`, `meaning_reviewed: true`, standard voices, no cloning and screening off. Capture/provider declarations are operator attestations; a JSON field or recording hash is not cryptographic proof that a provider or hardware path was used. Keep the corresponding capture and review notes privately for inspection. Local phone recording and analysis need no API credits. A rehearsal with pre-recorded/doubled provider audio must remain `provider_kind: double` and cannot pass the live acceptance gate; a new live provider flow still needs its separate approval.

Both **p50 and p95 must be strictly below 2,000ms** over at least ten distinct qualifying warm attempts, with **all warm attempts complete and zero observed failures**. The planner uses nearest-rank percentiles; with ten observations p95 is their maximum. Report first-route measurements separately. Ten warm observations are a small acceptance sample for the selected cases, not an accuracy or reliability certification.

The evaluator rejects duplicate observation IDs and duplicate `(recording_sha256, source_speech_end_sample)` pairs within one direction, even if someone changes the ID. Ten utterances in one recording can qualify when their speech-end indices differ. Keep signed latency values. A negative value is reported as overlap requiring review and cannot pass this final-turn benchmark; it is never clamped to zero.

Server first-PCM timings, STT-start timings, decoded RTC frames, browser render estimates, manually entered totals, synthetic tones and provider doubles cannot unlock this gate. Browser render and decoded boundaries remain useful diagnostics; they do not measure acoustic or electrical listener output. The existing offline `synthetic_local_rtc` evidence therefore remains unverified for this acceptance goal.

```powershell
.\server\.venv\Scripts\python.exe scripts/plan_latency_language_workflow.py --plan
# Add already-recorded local observation JSON files for offline assessment only:
.\server\.venv\Scripts\python.exe scripts/plan_latency_language_workflow.py --plan --evidence work/physical-observations.json
```

An evidence file can contain one observation or a list. The planner checks finite sample-derived timings and limits input size/count. Its output contains review eligibility, reason codes, sample counts, signed observed delays, p50/p95 and failure rate. It does not export recording paths, raw observation IDs, audio, account balances, provider endpoints or credentials. Define the test batch and configuration before collecting its results, then supply **every warm attempt from that batch**, including failures. Do not mix configurations or remove failed attempts to obtain a pass. Preserve older failed optimization batches as separate immutable evidence; they remain visible history rather than an all-time failure lock on a new, predeclared configuration.

For two-way coverage, review A→B and B→A as separate directions. A single successful direction does not certify the reverse direction. No English pivot is added: each requested target uses the source transcript directly, avoiding an extra translation and an extra request.

## Review prompts

The current latency workflow has four draft categories per source language: ordinary interpretation, explicit negation, names/colour associations, and a room identifier/time. All 40 are pending fluent source review and have no accepted target translation. The older `plan_language_matrix.py` still contains the following ten different draft prompts as a separate typed smoke reference; it neither runs tests nor overrides the physical gating order above.

| Source    | Focus                        | Intended everyday meaning                       |
| --------- | ---------------------------- | ----------------------------------------------- |
| Hindi     | Number and negation          | Meet at 10, not 11                              |
| Tamil     | Colour and preference        | Wants the blue book, rejects red                |
| Bengali   | Relative day and time        | Library tomorrow morning at 9, not today        |
| English   | Polite request and condition | Close the window after the call, not before     |
| Telugu    | Decimal and unit             | Bottle contains 1.5 litres, not 150 millilitres |
| Kannada   | Direction and sequence       | First turn left, then go straight 200 metres    |
| Malayalam | Names and associations       | Red book to Meena, green book to Ravi           |
| Marathi   | Past tense                   | Met at the park yesterday evening               |
| Gujarati  | Conditional plan             | Rain means indoors; otherwise the park          |
| Punjabi   | Mixed identifiers            | Meet in AM-204; network name Lotus Guest        |

For deeper accepted pairs, add contrast cases changing only one fact: 10→11, left→right, past→future or positive→negative. Preserve short questions as questions, reject invented names/dates, and ask the human speaker for context when ambiguous. Human review accepts equivalent natural wording; matching one exact target string is not required.

## Offline plan and individual limits

```powershell
.\server\.venv\Scripts\python.exe scripts/plan_language_matrix.py --plan
```

This legacy typed-matrix script reads no environment file, imports no application/provider client, opens no ledger and performs no network/audio operation. It supports no run, approve or renew action. Its JSON contains stable route IDs and SHA-256 hashes, source codepoint counts, stock voices and **unapproved individual** typed-flow proposals. Use the newer latency workflow for the current direction order and gates.

Each proposed two-member route has a 120-second approval window, at most **one MT attempt** for that exact source, **one standard TTS attempt / 200 synthesis characters**, **zero STT**, **zero enrollments** and **zero automatic retries**. This is not a combined allowance for all ninety routes. If target output exceeds its allowance or any step fails, stop and request a new explicit flow approval rather than silently widening the budget. Evon charges and actual invoices remain unknown until supplied; source-character counters do not measure model-token billing.

For each approved live route, record the case ID, actual source transcript when applicable, translated text, fluent meaning review, audible target-language result, route identity, first-PCM stage timing and completion/failure. Export Performance and Usage evidence separately. Record listener delay only with a stated shared-timebase method. Otherwise leave it unknown. A drafted matrix or offline fixture result must never become an automatic semantic pass.
