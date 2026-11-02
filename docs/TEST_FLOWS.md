# Local-first test flows

Run these gates in sequence. Use everyday conversations and standard voices. Multi-party interpretation and voice cloning wait until two-person speech works locally, on a second device and through the hosted interface. Each row is a separate check with an explicit result: **not run**, **pass**, **fail** or **blocked**. Prepared code and simulated output are not a completed listening test.

Inspecting plans, opening reports and running fixture tests makes no provider calls. Each actual provider flow still needs a separate bounded approval; do not run the entire list automatically.

## Stage gates

| Gate | How to test | Pass condition | Evidence to keep |
| --- | --- | --- | --- |
| **0. Local setup** | Start the local frontend/API; open Home, Test lab, Performance and Usage. Run automated unit/contract checks and local synthetic RTC checks. | Pages and health/readiness respond; fixture RTC checks report intended subscriptions and audio; missing live configuration is clear. | App revision, test output and redacted readiness. Synthetic RTC proves transport mechanics only. |
| **1. Two-browser original audio** | Start the dedicated local transport mode with self-hosted LiveKit. Join one room from two browser profiles, use headphones and the same language; intentionally unmute one person at a time. | Both hear the other person's original audio, have no self-echo, and mute/leave stops further source audio. No STT/MT/TTS calls or translation captions are claimed. | Human listening result, browser/network metrics and zero provider-unit change. |
| **2. Typed interpretation** | With the actual Evon endpoint/model and speech key configured, send one dataset sentence at a time between Hindi and Tamil members using standard voices. | Target text preserves meaning, values and conditions; listener hears one target-language output. Typed input bypasses STT. | Case ID, exact output, bilingual review, branch status and server timing export. |
| **3. Two-way microphone speech** | Hindi A speaks short complete phrases to Tamil B; then reverse. Test the scripts below, deliberate corrections and natural pauses. | Accurate source transcript, understandable target speech, correct target-only routing, no self-echo/double playback and visible errors on failure. | Separate source-transcription and target-meaning assessments; failures and exact latency boundary. |
| **4. Second device** | Repeat original audio and two-way interpretation with one extra device using a deliberately configured reachable HTTPS frontend/API and WSS LiveKit. | Microphone permission works on both devices, ICE/media connect, both directions work, reconnect recovers without stale speech. | Device/browser/network details, track/routing observations, browser metrics and listener result. |
| **5. Sites interface** | Build the frontend against a reachable HTTPS API; permit the exact Sites origin. Join the same backend room from the Sites interface on both devices. | The UI reports live backend/RTC connection and repeats gate 3 successfully. | Build/backend identity, exact origin, test results and exports. A scripted static preview alone does not pass this gate. |
| **6. Multi-party** | After the two-person gates pass, add Bengali C. One speaker at a time first; then short controlled overlap. Add a same-language listener as a separate variation. | All six directed hi/ta/bn routes work; no self-output or wrong-language audio; same-language audio forwards correctly; one synthesis per distinct target language. | Six-route checklist, provider request counts, failures and timings for each directed branch. |
| **7. Voice cloning** | Only after the preceding gates: explicitly consent to use your own clean 5–30-second spoken PCM reference. Run one enrollment and one synthesis before trying cloned interpretation. | Enrollment succeeds, speaker reviews similarity, fluent listener reviews intelligibility; standard-voice fallback and deletion work. | Separate consent record and similarity/intelligibility review; no raw reference or embedding in exported diagnostics. |

The local transport launcher is separate from the scripted demo and from live interpretation. Demo rooms display canned participants/translations and do not connect two microphones. Live interpretation rejects missing provider setup instead of returning a pretend translation.

## Local sequence

From the project directory, complete dependency setup once:

```powershell
.\scripts\setup.ps1
npm run dev:local
```

The local launcher starts self-hosted LiveKit, the Python API and the frontend for original-audio testing. The terminal prints the actual frontend and API addresses. Follow [LOCAL_TESTING.md](LOCAL_TESTING.md) for installation details and the two-browser procedure. Open `/#/tests` for the Test lab.

Run the three provider-free RTC fixture checks against the local LiveKit server with:

```powershell
npm run test:rtc
```

These scripts publish generated tones through actual local WebRTC and use provider doubles. They do not open microphones, call Gnani/Evon or demonstrate real translation. Keep this evidence separate from human speech acceptance.

The separate local provider-reporting workspace is:

```powershell
npm run dev:checks
```

Open `/#/usage` and `/#/performance`; live interpretation remains blocked when required configuration is missing or no approved flow exists. The reporting workspace uses loopback, normally port 5180. Keep the call tab open when inspecting its browser-network metrics on Performance. Stop the current launcher before switching modes, because both use the same default frontend port.

## Everyday speech scripts

The 18 cases in `evaluation/everyday_cases.jsonl` provide draft Hindi→Tamil, Tamil→Hindi, Bengali→Hindi and Hindi→Bengali references. Review meaning rather than requiring an identical target sentence. A fluent reviewer must check these references before treating them as trusted answers.

| Test | Say or type | Expected meaning / outcome |
| --- | --- | --- |
| Day and time | “कल सुबह 10 बजे पार्क के मुख्य दरवाजे पर मिलते हैं, आज नहीं।” | Tomorrow at 10 AM, main park entrance; today is explicitly rejected. No invented calendar date. |
| Negation and condition | “मेरे फ़ोन करने तक घर से मत निकलना।” | Stay home until the speaker calls. Dropping either “not” or “until” is a failure. |
| Counts and association | “बैग में 12 नीली और 8 सफेद पेंसिलें हैं।” | 12 blue pencils, 8 white pencils, in the bag. Swapped colours fail even if both numbers appear. |
| Polite request | “क्या आप खिड़की खोल सकते हैं?” | A question/request to open the window, not a claim that someone already opened it. |
| Code mixing | “कमरा AM-204 है। कृपया Wi-Fi का नाम फिर से बताइए।” | Preserve AM-204 and ask for the network name again. Do not change “name” to “password.” |
| Conditional plans | “यदि बारिश हुई तो हम घर के अंदर खेलेंगे, वरना पार्क जाएँगे।” | Rain → indoors; otherwise → park. Do not turn a conditional plan into a weather prediction. |
| Direction and unit | “முதலில் இடதுபுறம் திரும்பி, பிறகு 200 மீட்டர் நேராகச் செல்லுங்கள்.” | First left, then straight for 200 metres. Wrong turn, unit or sequence fails. |
| Correction | “நான் இரண்டாவது தளத்தில் இருக்கிறேன், மூன்றாவது தளத்தில் இல்லை.” | Second floor is correct; third floor is rejected. |
| Decimal and unit | “இந்தப் பாட்டிலில் 1.5 லிட்டர் தண்ணீர் உள்ளது, 150 மில்லிலிட்டர் இல்லை.” | 1.5 litres is correct, 150 millilitres is rejected. Numeral presence alone is insufficient. |
| Names and colours | “மீனாவிடம் சிவப்பு நோட்டுப் புத்தகத்தைக் கொடுங்கள்; பச்சை நோட்டுப் புத்தகம் ரவிக்கானது.” | Red notebook → Meena, green notebook → Ravi. Names and associations remain intact. |
| Past tense | “कल शाम हम पार्क में मिले थे।” | Yesterday evening, a completed meeting in the park. Past tense resolves the Hindi word “कल.” |
| Unclear context | “कल?” after a pause | Treat as an ambiguity review: the word alone does not establish yesterday/tomorrow. Ask the human speaker for context; the current application does not promise automatic clarification. Record a confidently invented date as a failure. |

For contrast, repeat an approved test after changing only **10 to 11**, **left to right**, or **not today to today**. The listener should identify the changed meaning. Do not replay the whole dataset just to obtain a faster timing.

## Recovery variations

Use fixture providers for forced faults. Any repetition with real providers is its own approved flow.

1. **Mute:** A begins a phrase, then mutes. B hears no further source audio after the server applies mute; already played audio cannot be recalled. Queued future work must be cancelled.
2. **Leave:** A leaves during a pending phrase. No new output for that membership arrives after cancellation; remaining members can continue.
3. **Language change:** Switch B's selected language while idle; the next phrase uses the new route and the prior subscription is removed.
4. **Network interruption:** Disconnect/reconnect one browser. Show connection state, recover deliberately and reject stale audio from the departed membership.
5. **Permission/autoplay denial:** Deny microphone permission or browser playback. Show an understandable action to enable it; do not display simulated speech success.
6. **Provider failure or exhausted grant:** The branch visibly fails/stops, records the error stage and does not switch to a canned translation or silently retry a denied request.
7. **Controlled overlap:** Two speakers say distinct short phrases. Preserve speaker identities and per-speaker sequence; record intelligibility and queue saturation separately from single-speaker results.

## Recording latency fairly

The Performance page reports server STT processing, queue, MT and first-PCM boundaries, plus call-tab network statistics when available. Separate typed from microphone input and standard from cloned voices. Include completed, failed and cancelled branch counts. Record the number of observations alongside p50/p95; a single result is one sample, not a dependable percentile benchmark.

For actual listener delay, make a consented synchronized capture containing the source speech and receiver's audible output. Mark **last source-speech sample → first audible translated sample**, record the method, and retain the capture privately. Report overlap separately if the output starts before the source phrase ends. A browser RTT or server dispatch duration cannot substitute for this measurement. Agree a target before evaluating; do not label the blueprint's 800-ms ambition as already achieved.

Minimum per-flow record: gate/case ID, app revision, mode, language direction, input kind, voice mode, devices/browser/network, source duration, exact transcript/output reviewed, route, result/failure reason, sample count and timestamp. Export room timings from Performance; usage counters remain separate from provider-billed amounts.

## Local and hosted boundaries

On a second device, `localhost` means that second device. A server bound to `127.0.0.1` is intentionally unreachable from it. Configure LAN access and trusted HTTPS/WSS or use a secured reachable test endpoint; do not disable browser certificate checks to make microphone access appear to work.

Sites serves the frontend. It cannot run the Python room/translation agent or LiveKit media server, and a hosted frontend cannot use the primary computer's loopback backend. A publicly reachable HTTPS/WSS backend, correct origin allowlist and working media ports are prerequisites for gate 5. Zoho/server deployment is a later step; choose a service that actually provides the required networking before assuming SSH access or UDP support.

## Existing speech-only evidence

The separately approved Gnani TTS→STT check passed once on 24 October 2026 with “नमस्ते भारत।”. It measured only a short synthesis/transcription round trip, not a two-person interpreted meeting. See [VALIDATION.md](VALIDATION.md).

```powershell
.\server\.venv\Scripts\python.exe scripts/check_gnani.py --plan
```

The plan creates no API call. The old approved grant is closed. Repeating that speech check, running MT or enrolling a voice needs a new specific approval. Gnani's [REST STT instructions](https://docs.gnani.ai/api/STT/speech-to-text) cover short uploaded audio; the application uses documented [WebSocket STT](https://docs.gnani.ai/api/STT/stt-websocket) for paced live PCM. Provider reports do not supply a verified billed-credit amount in the documented transcript response.
