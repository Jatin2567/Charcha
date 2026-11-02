# Verification and remaining live checks

## Screening latency checkpoint — 29 October 2026

The full 64,600-sample AASIST input and experimental thresholds remain unchanged. Matched local CPU diagnostics showed 20 warm full-analysis medians of **403.500 ms (one thread), 268.460 ms (two) and 317.499 ms (four)**. Two concurrent callers also favored two threads: **810.884 → 524.416 ms** per-analysis median, with six pair-completion observations per setting. Diagnostic logits/scores/flags matched within declared tolerances; no genuine-speech or representative accuracy claim follows. The local no-provider launcher now selects two CPU threads; other deployment defaults remain one.

Adding the unchanged 4,037.5 ms collection duration gives **4,441.000 → 4,305.960 ms**, only about **3.04% lower**. This arithmetic estimate excludes queueing, recognizer readiness and listener playback. Separate 0.5/1/2/3-second repeated-prefix experiments scored 25 synthetic windows; all 20 short flags matched the native flags, but maximum score drift was **0.134706**. Short-input live activation is disabled. Strict dataset preflight remains blocked and accuracy is null.

**99 focused backend checks**, **133 frontend checks** and the production build passed. Local RTC enforcement with controlled verdicts assessed exactly 64,600 samples before release, withheld suspicious/unknown windows, and discarded partial audio on mute. Its allowed synthetic PCM reached the receiver in **4,090.54 ms** from source capture. Actual-model monitor on two threads forwarded synthetic audio in **168.70 ms**, with **306.569 ms** analysis after the input window. These are individual same-process fixtures; decoder startup silence can precede capture timing. They are not acoustic listener, translation or accuracy benchmarks. A local status read confirmed model ready, two CPU threads, window 4,037.5 ms and zero provider calls.

Evidence: `work/screening-latency/compute-20261029.json`, `compute-concurrent-20261029.json`, `duration-diagnostics.json`, `duration-preflight.json`, `rtc-enforce-20261029.json` and `rtc-monitor-20261029.json`. See [SCREENING_LATENCY.md](SCREENING_LATENCY.md) for reproduction and accuracy limits. No provider/API credits, paid servers, new model downloads or cloning were used.

## Modal preparation checkpoint — 29 October 2026

The pinned Modal deployment and runtime helper are prepared locally. **34 lifecycle tests** cover expiry, CPU cache preparation, metadata/size checks, GPU admission and process cleanup. **129 focused authentication/benchmark/resilience tests** passed with provider doubles, including the new Modal proxy credential pair. The actual Modal 1.6.3 SDK imports and validates the declaration without deployment. It rejected an explicit retry option on Web Functions; that unsupported option was removed, while the CPU download retains zero retries.

The full backend run completed with **628 passing tests and one Windows file-access failure** in an existing LAN stack directory rename. That single test passed on immediate isolated rerun with a fresh workspace directory. The initial failure remains part of the record; no production LAN behaviour was changed. All **133 frontend tests** and the TypeScript/Vite build passed after the journal update. The existing bundle-size advisory and Starlette deprecation remain.

The owner completed browser authorization for a temporary Modal CLI profile. Read-only billing showed zero metered and billed usage; the signed-in workspace advertised only **$1/month included compute and a $1 usage limit**, with an Add payment method prompt. The public $30 offer is not treated as this account's verified allowance. No cloud app build/deployment, CPU weight download, GPU invocation, inference, Gnani request, payment-method change or spending-limit change occurred. Actual credit availability, GPU eligibility and a verified zero out-of-pocket spend limit remain unresolved. See [MODAL_TESTING.md](MODAL_TESTING.md).

The earlier complete local checkpoints below remain historical evidence.

Verification updated on **28 October 2026**, on the local Windows development environment. Local Docker image builds and HTTPS/WSS signaling now pass; GPU model/image metadata is pinned and the serving configuration validates without starting it. Windows browser certificate trust was declined by the owner and remains deferred. The previously measured cold-start repair is retained unchanged below. Human listening, real speech accuracy and physical listener latency remain separate acceptance evidence.

Later five-language preparation: **29 planner/matrix tests** (21 new) and **25 existing screening evaluator/preflight tests** passed using workspace temporary folders. The planner produces 20 directed routes and 60 unapproved, unmeasured observations for Hindi, Tamil, Bengali, Telugu and Marathi. The 40-slot screening manifest correctly fails readiness because recordings, consent, label evidence and split groups are missing; accuracy remains null. These checks made no provider or inference calls. The suite totals below record the earlier full checkpoint.

The updated Performance/Test lab interface passed all **133 frontend tests** and the TypeScript/Vite production build. Browser review confirmed the five-language plan, budget limits and changing the draft script from Hindi→Tamil to Marathi→Telugu. The frontend-only preview routed API requests to an unused local port; no speech service was reachable. Saved UI proof: `work/five-language/performance-plan.jpg`.

GCP access check: a request for one global GPU was declined with zero granted and `NOT_ENOUGH_USAGE_HISTORY` eligibility. An instance listing confirmed no VMs. Budget authorization is ₹5,000 GCP overall, ₹2,500 for latency; the separate ₹55.35 Gnani speech figure is reference arithmetic for proposed caps, not approved usage or verified billing. Actual five-language E2E testing has not run.

| Area                                        | Result            | What this establishes                                                                                                                                                                                         |
| ------------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python API/provider/lifecycle suite         | 534 passing tests | Full suite includes local certificate generation, HTTPS/WSS probe guards, immutable GPU configuration, host/stop-plan validation and the exact screening-window regression. Provider integrations use test doubles. No real provider calls. |
| Frontend suite                              | 133 passing tests | Includes four grouped-latency tests: input/direction/voice separation, failed/cancelled attempts, missing/invalid times and safe exports. Existing cold-start, journal and interface-service tests also pass. |
| TypeScript and Vite production build        | Passed | The updated comparison page compiles and produces the static frontend. Existing large-chunk advisory remains; no build error. |
| Ten-language coverage plan | Fixture checks passed; live quality pending | All 90 directed routes have mocked translation labels/recipient checks; ten STT locale headers and stock-voice payloads checked. The local coverage table fits desktop and scrolls within its container at phone width. No live translation or all-language listening pass is claimed. |
| Two-peer original-audio startup, 28 October | Three baseline and three repaired runs passed | Six directions per group: median capture→received PCM fell from 686.500 ms to 210.535 ms in fresh comparable tests. Routing, server mute, receiver detach and unmute passed in all six runs. The earlier 12,132.83 / 4,669.78 ms incident is historical and excluded from these medians. |
| Local AASIST CPU classifier | Execution and abstention smoke checks passed | Pinned ONNX model loads locally; short, silent and clipped fixtures stay unknown. Warm compute was 382.273–428.804 ms across five runs for a 4,037.5 ms window. Synthetic signals establish no speech-detection accuracy. |
| Actual-model screening over local RTC | 28 October monitor fixture passed | Original synthetic audio arrived before classification: 158.74 ms source-capture→first received PCM. Model compute was 566.684 ms after a 4,037.5 ms input window; monitor hold was zero. The earlier loaded run was 294.67 ms / 2,417.732 ms compute. These are individual fixtures, not acoustic, translation or speech-accuracy benchmarks. |
| Local RTC enforcement gate | Controlled-verdict fixture passed | A test double exercised allow, suspicious and unknown paths; partial and disallowed windows were withheld. Allowed capture→received PCM was 4,343.46 ms, including window collection. This establishes routing/gating behavior, not classifier quality. |
| Browser receiver probe | One observation completed | 3,022 ms from a request in one browser to decoded dedicated-tone energy, including setup and polling. The browser reported this result; no physical speaker-output or translation end-to-end measurement is claimed. |
| Browser media connection, 27 October | Passed in the in-app browser | Media established with the microphone off; a generated remote tone reached a playing browser audio element (`readyState=4`, unmuted, advancing time); physical listening and native-Chrome human acceptance remain separate |
| Real local WebRTC, three distinct languages | Passed            | Three synthetic PCM publishers; six directed provider-double branches; two non-silent appropriate tracks per listener; no self/original/wrong-language subscriptions                                          |
| Same-language transport experiment          | Passed            | Hindi/Hindi/Tamil forwarding and resampling, shared target language generation, mute/unmute and expiry gates using synthetic PCM and provider doubles                                                         |
| Browser acceptance journey                  | Passed            | Create, language selection, consent, join, six scripted shared turns, translated/original views, understanding confirmation, reconnect snapshot, leave, recap and explicit save                               |
| Responsive meeting                          | Checked           | Mobile participant stage scrolls; essential controls remain accessible; transcript panel can be closed                                                                                                        |
| Performance & readiness browser journey     | Passed            | Separate report tab retains room access while the call stays connected; 14 scripted branch rows remain excluded from live percentiles; language filtering, setup scrolling and filtered JSON download checked |
| Responsive performance page                 | Checked           | Mobile page width stays within its viewport; wide tables scroll independently; desktop summary grid and setup reference reviewed                                                                              |

The local screening and real RTC checks do **not** call Gnani or Evon or start a paid server. Their generated test audio is only a signal/transport fixture. None of these results establishes actual deepfake accuracy, translation accuracy, voice-clone similarity, physical end-to-end listener latency or external provider account access.

The earlier browser failure was an ICE candidate mismatch: forcing the advertised media address to 127.0.0.1 was insufficient, and mDNS handling alone did not fix it. The local launcher now lets LiveKit select usable local interfaces and explicitly includes loopback and mDNS candidates, while retaining localhost HTTP/API signaling. The successful two-peer timing capture is source capture→received non-silent PCM in one process and includes media negotiation/codec buffering. It is not a microphone-to-headphone or translated-speech latency benchmark. Follow [LOCAL_TESTING.md](LOCAL_TESTING.md#exactly-two-chrome-users-on-one-windows-computer) for the remaining two-user Chrome check.

The raw-audio regression retains production unpublish-on-mute. The Python receiver test originally kept an unbounded PCM queue and did not handle `TrackUnsubscribed`, so it counted stale buffered samples after mute. Its corrected receiver bounds the queue and detaches on unsubscribe, matching browser behavior. The check waits at most five seconds for confirmed receiver detachment, asserts the server output and reader are absent and no new PCM arrives while muted, then requires actual received audio within six seconds of unmute. The historical incident had a 256.57 ms mute-to-detach observation and cold-start first-audio observations of 12,132.83 ms and 4,669.78 ms. Those values remain visible as prior evidence, but different host load makes them unsuitable for computing the repair's percentage improvement.

The renewed six-route fixture initially exposed a first-output subscription race. Production PCM delivery now waits up to five seconds for a subscriber, before consuming the synthesis generator, and rechecks active recipients. Original audio has a six-second bounded startup queue with visible overflow errors. All six directed routes then passed with the unchanged two-second synthesis fixture. The mixed same-language/resampling/mute/expiry fixture also passed; its initial completion deadline is now twenty seconds to account for bounded negotiation, and it asserts that the initial turn actually completes. These are fixture results, not translated-speech or human-listening acceptance.

Performance reporting retains at most 1,000 terminal branches per room. Automated checks cover exact-room authorization, configuration redaction, missing STT markers, exclusion of simulated/forwarded/failed/cancelled branches, queue cancellation, partial failure and first-PCM timing distinct from playout completion. Typed same-language cloning bypasses MT and keeps embeddings out of reports. Browser network-stat conversion is checked with standard-shaped fixtures; its real-device collection still needs the live call check. The STT timer is receipt of a processing event to receipt of a transcript, not a measured speech-end boundary. See [GO_LIVE.md](GO_LIVE.md) for exact definitions and required inputs.

## Docker, HTTPS and pinned GPU preparation — 28 October

- Both Docker application images built. The four-service local LAN stack started
  and the API became healthy. Both nginx configurations and the installed API
  dependencies (`pip check`) passed. Only this owned test stack was stopped;
  its volume was retained.
- The explicit-CA HTTPS probe passed frontend/API validation and two authenticated
  WSS signaling joins, then removed its temporary memberships. It negotiated no
  audio and changed no Windows trust. Evidence:
  `work/pre-gpu/lan-https-signaling-20261028.json`.
- The owner declined the Windows certificate import. Trust was confirmed absent;
  the existing network profile and firewall were not changed. Certificates and
  the exact-peer firewall helper are prepared. Real two-device media and listening
  remain pending; see [TWO_DEVICE_TESTING.md](TWO_DEVICE_TESTING.md).
- The native RTC suite passed original audio in both directions, six simulated
  translation routes, shared-language routing, resampling, mute/unmute and expiry.
  Latest raw observations were **213.96 / 181.77 ms**; they are single-run
  diagnostics, not a new matched before/after experiment. Evidence:
  `work/pre-gpu/raw-rtc-20261028.json`.
- The CPU classifier smoke check passed five synthetic fixtures, with warm compute
  **317.345–348.390 ms**. Actual-model monitoring forwarded at **167.31 ms** and
  classified after a **4,037.5 ms** window, with **993.438 ms** computation in that
  run. This does not establish speech accuracy or comparable latency under load.
- An enforcement harness failure was reproduced: startup decoder silence enters
  the screening window before the later tone timer, so a fixed 3,900 ms wall-clock
  assertion was invalid. The repaired test requires exactly **64,600 decoded
  samples** and an allow verdict before any received output. It passed, as did
  suspicious/unknown withholding and partial-window discard on mute. Production
  enforcement was unchanged. Failure evidence is retained at
  `work/local/screening-enforce-legacy-boundary-failure.log`; the repaired report
  is `work/pre-gpu/screening-enforce-20261028.json`.
- Evon model and image metadata are pinned and native configuration handling was
  reviewed. Generated GPU Compose schema validation passed with isolated dummy
  credentials and an explicit empty environment file. No GPU image layers,
  model tensors or inference were downloaded/run. Host/stop-plan validation is
  offline; actual loading, translation and GPU latency remain pending.
- Test lab and Developer journal were checked in the browser. Journal dates now
  use the recorded date rather than a hard-coded 24 October label. Performance's
  first-synthesis-PCM description explicitly includes output/subscriber setup.

No speech-provider calls, paid servers, microphone capture or cloning were used
for this checkpoint. The latest complete test counts appear in the table above.

## Earlier pre-GPU preparation checkpoint

- **471 backend tests and 133 frontend tests passed; production build passed.**
  The full backend run first exposed an older 90-language-route mock that omitted
  `finish_reason`; updating it to a completed response restored the full pass.
  Runtime response validation was not relaxed to accommodate the mock.
- **Evon adapter:** thinking disabled, invalid input rejected before usage,
  incomplete/refused/tool/reasoning responses rejected before synthesis, cancellation
  propagated, no automatic MT retry. Automated provider requests used test doubles.
- **Portable GPU package:** `scripts/evon_benchmark.py` produces an offline two-case
  Hindi/Tamil plan. Execution needs the exact approved plan hash and explicit GPU
  cost acknowledgement. `scripts/evon_prepare.py` requires immutable model/image
  pins and produces private loopback serving configuration. No image/weight download,
  GPU launch or real inference was performed. See [GPU_TESTING.md](GPU_TESTING.md).
- **Two-device preparation:** 17 focused tests covered actual in-memory TLS
  handshakes, key/IP SAN validation, isolated credentials and zero-provider mode.
  Docker Desktop startup was attempted, but its Linux engine pipe remained
  unavailable; no container build/run is claimed. Valid device-trusted certificates,
  networking and real listening remain pending. See [TWO_DEVICE_TESTING.md](TWO_DEVICE_TESTING.md).
- **Detector evidence:** the preflight validates declared consent/evidence, audio
  duplicates and speaker/source split separation without inference. Default metadata
  errors stop before model construction. Held-out/declared evaluation results have
  a separate headline; pooled calibration results stay labelled. Failed recordings
  remain in all-labelled coverage. The placeholder manifest was correctly rejected
  with `ready_for_scoring: false`, `accuracy: null`, zero model/provider calls.
- **Browser verification:** Test lab rendered the new preparation panel in the
  local raw-audio workspace; its JSON export was downloaded and the Performance
  page displayed grouped-timing empty states without invented measurements.
  Four frontend tests cover group accounting and sanitized exports, including
  partial audio totals when recognition markers are missing. No microphone was opened.
- **Limits:** these tests do not establish Evon runtime compatibility, multilingual
  quality, detector accuracy, two-device audio, acoustic latency or voice-clone quality.
  Voice cloning remains deferred. Only local app processes were used; no provider
  credits or paid servers were used.

## Cold-start repair: fresh before and after

The first decoded source frames can contain exact-zero PCM before the publisher has captured a sound. The relay negotiated its output, then replayed this leading backlog at real-time pace ahead of the first actual signal. The fix still uses those frames to establish a subscriber, but discards **only leading all-zero frames** at the forwarding stage. A one-unit PCM sample is preserved: this is not a speech-volume threshold. Once the first nonzero source frame has arrived, later pauses remain intact. The raw transport output queue is now 60 ms instead of the 250 ms synthesis-oriented queue; synthesis keeps its existing queue. Subscriber readiness, room/recipient checks, screening eligibility, source mute and queue bounds still apply.

The benchmark runs two synthetic publishers and their relay in one local process against the local LiveKit server. Each run creates fresh memberships, connects both peers and waits one second before the first source capture. Screening is off for this isolated comparison. Both groups use the same harness and timing boundary; all three runs per group are retained. No provider API, microphone or paid server is involved.

| Fresh comparison | Before | After |
| --- | ---: | ---: |
| Passed runs / attempted | 3 / 3 | 3 / 3 |
| Measured directions | 6 | 6 |
| Median capture → received non-silent PCM | 686.500 ms | 210.535 ms |
| Observed minimum–maximum | 322.65–1,149.82 ms | 172.18–379.97 ms |

Baseline directions were **1,149.82, 383.46, 641.79, 322.65, 731.21 and 960.51 ms**. Repaired directions were **379.97, 370.96, 204.25, 175.03, 216.82 and 172.18 ms**. The recorded median is approximately **69.3% lower**. This is a descriptive six-sample comparison, not a reliable p95 or a production guarantee. Every run also passed routing, mute, receiver detach and audio restoration checks; no failed trial was discarded.

Instrumentation supports a backlog explanation. In the first baseline trace, the relay received signal at 113.19 ms after source capture but did not submit its first non-silent output frame until 999.37 ms: an **886.18 ms gap**. Output publication itself took 5.13 ms. In the first repaired trace those markers were 111.59 ms and 146.63 ms, a **35.04 ms gap**. Submission to the relay's output source is an intermediate boundary, distinct from received PCM and physical playback.

The source reports are `work/cold-start/before-01.json` through `before-03.json` and `after-01.json` through `after-03.json`. `work/cold-start/historical-before.json` preserves the earlier 12,132.83 / 4,669.78 ms incident separately. The Performance page's saved evidence contract is `web/src/data/coldStartResults.json`; historical rows and failed runs never enter the fresh before/after summaries. Its report is not current-room telemetry.

The isolated repair does not certify microphone-to-headphone latency, translation, noisy real speech, concurrent screening load or multiple physical devices. A separate actual-model monitor smoke check after the repair received its first synthetic PCM at 158.74 ms; the detector subsequently used 566.684 ms of CPU work for a 4,037.5 ms input window. This is not deepfake accuracy evidence. Voice cloning remains deferred.

## Local screening and measurement boundaries

The optional model is the MIT-licensed `SpeechAntiSpoofingBenchmarks/AASIST` ONNX export, pinned to revision `16774d458d86d2a021ae31646c1bf66a5331b53e` and verified by SHA-256 before loading. It is approximately 1.62 MB and runs with the CPU execution provider. This is a third-party, NAVER-origin model, **not an Indian-trained detector**. Installation is an explicit free artifact download; ordinary application startup and analysis perform no model-network calls.

The five warm smoke timings are 424.646, 428.804, 382.273, 397.390 and 398.255 ms. These follow a measured 888.969 ms model load and use generated signals. They must not be presented as speech-recognition or deepfake-detection latency percentiles. During concurrent local RTC work, the same classifier took 2,417.732 ms on one 4,037.5 ms window. The difference demonstrates that laptop load matters; isolated compute is not a live-call latency guarantee.

`monitor` forwards audio while screening reports later, so its gate hold is zero. `enforce` collects a complete 4,037.5 ms window and only releases an experimentally low-score result; suspicious, unknown, incomplete or overloaded windows remain withheld. The controlled enforcement run measured 4,037.65 ms of hold and 4,343.46 ms from synthetic source capture to first received PCM. Its verdicts came from a deterministic test double. No real-human allow rate or synthetic-speech catch rate follows from that run. Strict window enforcement cannot currently support an under-800-ms whole-path promise.

Signal diagnostics include pitch and consecutive-frame jitter/shimmer proxies. They are not clinical cycle-level measurements and do not establish that a voice is human. The learned score is uncalibrated; missing/corrupt models, insufficient signal and incomplete analysis preserve `unknown`. The smoke evaluation contains five diagnostic fixtures and zero labelled nonfixture speech samples, so its coverage, false-alarm, miss-rate and accuracy fields are `null` rather than fabricated zeros or percentages. See [the screening evaluation protocol](../evaluation/audio_screening.md).

Three different timing families remain separate in the interface and exports:

1. **Server pipeline:** transcript/queue/MT/TTS-first-PCM boundaries, with the existing STT proxy.
2. **Browser receiver probe:** one monotonic browser clock from an explicit local-tone request to decoded signal detection. Its single 3,022 ms browser observation includes request/setup/RTC/detection, and excludes microphone capture, translation and physical speaker output. Polling/main-thread delay is part of the result. Failed and cancelled probes remain visible.
3. **Manual shared recording:** for original audio, annotate the same marker onset at source and receiver; for translation, annotate source phrase-end and first translated output. Both positions must use one synchronized recording and include its anonymous reference and duration. Separate device clocks and network round-trip time are not substitutes. No such human-recorded acceptance sample has been validated yet.

The Audio lab validates mono 16 kHz, 16-bit PCM WAV before a consented local upload, permits up to 30 seconds, and keeps generated silence/tone/clipping fixtures distinct from speech evaluation. Browser reports exclude raw audio, filenames and credentials; room-report exports also omit participant/room identities. The Development page records these checks and keeps unresolved speech accuracy and device acceptance visible.

Screening evidence files are `work/audio-screening-smoke.json`, `work/local/screening-rtc-model-monitor.json` and `work/local/screening-rtc-enforce.json`. The fresh cold-start comparison uses the six reports in `work/cold-start/` listed above. `work/local/transport-check-under-test-load.json` and the preserved historical report are earlier captures, not substitutes for the matched comparison.

## Real-speech collection preparation — 29 October 2026

The [real-speech kit](REAL_SPEECH_TEST_KIT.md) now prepares 60 original-source
slots: six human and six standard, non-cloned AI clips per language in Hindi,
Tamil, Bengali, Telugu and Marathi. Native-script drafts and English meanings
require fluent review. Different A/B identities and different C/E scripts keep
preparation separate from evaluation, including across languages. Original audio,
consent/provenance logs and the completed checklist stay in ignored `work/`.

The checker requires declared permission and independent origin evidence, stock
voice/model identifiers, consistent anonymous groups, 8–20-second mono 16 kHz
16-bit PCM WAVs, no duplicate decoded audio and no cross-split source/speaker or
declared stock-voice reuse. It cannot authenticate the declarations itself.
The bounded study validates the entire dataset before one CPU model load, retains
at most 60 sources and 300 paired analysis calls, and reports evaluation-only
false alarms, misses, per-class unknowns/errors/unattempted rows, coverage and
group counts. Calibration is separate. Short prefixes remain lab-only inputs;
no policy, threshold or live window changes follow from the report.

Fresh focused checks passed **101 backend tests** with **one Windows symlink
test skipped**, plus **four Development-page tests** and the production frontend
build. Backend fixtures are fabricated WAVs/model doubles, not labelled speech
accuracy evidence. The first restricted Windows frontend run could not load its
temporary transform cache; the normal-permission rerun passed. The build retains
the existing large-chunk advisory; the backend emits the existing Starlette
deprecation warning.

The actual default study plan and empty-kit checks were exercised. Evidence:
`work/speech-study-plan-20261029.json`,
`work/speech-study-pending-blocked-20261029.json` and
`work/speech-kit-checked-empty-20261029.json`. The missing recordings keep
`ready_for_scoring: false`; no checked manifest was written. All three commands
report zero provider calls and zero model inferences. No real speech was
collected, generated or scored, no GPU was started and no voice cloning occurred.
The 60-source pilot has only one evaluation identity per class/language; even
successful collection cannot by itself establish representative accuracy or
justify shortening the detector window.

## Public human-speech evaluation — 29 October 2026

The [public human pilot](PUBLIC_HUMAN_SCREENING.md) collected ten publisher-described
FLEURS human readings in each of Hindi, Tamil, Bengali, Telugu and Marathi,
pinning revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd` and CC BY 4.0
attribution. The successful streamed collection transferred 48,667,201 body
bytes, preserved originals and created PCM16 analysis copies without resampling
or gain changes. No speaker IDs are supplied by this public source; counts of
independent speakers and personally reverified recording consent stay unknown.

The actual installed CPU model completed all 250 analysis calls in 64.57 seconds
with no failed or unattempted comparisons. The native 4,037.5 ms baseline allowed
24 human clips, falsely flagged 14 and abstained on 12. Its median compute was
256.175 ms; model loading took 1,100.578 ms. Short prefixes changed 40/50, 20/50,
16/50 and 9/50 flags at 0.5, 1, 2 and 3 seconds respectively. The study recorded
212 successfully scored model windows; some short inputs abstained before native
inference. Analysis attempts are not an exact native-failure counter.

This is a failed human automatic-blocking baseline, not a successful deepfake
accuracy benchmark. AI detection, misses and overall accuracy remain unknown
because no AI recordings were included. The live window and thresholds are
unchanged; monitor mode is recommended while investigating performance with
separate calibration and synthetic-evaluation data. CPU time excludes audio
collection, translation, transport and physical playback.

The saved Performance/Audio lab panel exports sanitized aggregates and preserves
unknown speaker counts and AI metrics. Software validation passed **115 focused
backend tests**, **11 frontend tests** and the production build. Tests use
fabricated WAVs/fake HTTP/model doubles; these passing checks do not override
the actual poor human model result. The existing Starlette deprecation and
frontend large-chunk advisory remain. Browser review verified the actual five
language rows, prefix disclosure and monitor recommendation. A 390-pixel viewport
kept horizontal scrolling inside the table without widening the document.

Evidence is under `work/public-human-fleurs-20261029-v2/`, with model/source hashes
in `screening-study-01.json`, the local source manifest and `collection-report.json`.
The earlier partial import is retained separately. The source-controlled
`web/src/data/publicHumanScreeningResults.json` contains only safe aggregate
results. Provider calls and paid-server usage were zero; no model training,
voice cloning or cloud resource launch occurred.

## Still requires your accounts/infrastructure

1. Standard Gnani STT/TTS passed one approved local speech test. Voice-cloning access, a LiveKit deployment and a served Evon endpoint still require acceptance.
2. Verify both directions with actual Hindi and Tamil speakers, then Bengali fan-out.
3. Check voice/model IDs, quotas, streaming permissions, reference quality and cross-language cloning on the account being used.
4. Collect actual latency and cost under the intended network and speech concurrency. The UI's server timing boundary is distinct from audible receiver playback.
5. Obtain bilingual review of the synthetic evaluation scripts and then review actual recorded outputs. Draft gold text is not certified ground truth.
6. Evaluate the detector on consented, held-out Indian-language human speech, unseen synthesis, replay and noise. Report unknown coverage alongside false alarms and misses; tune thresholds on a separate development split. Voice cloning stays deferred until the standard-voice and device checks pass.

## Deployment limits

The local Docker Linux engine now responds. API and web images built, all four LAN containers started, and HTTPS frontend/API plus two authenticated WSS joins passed with an explicitly supplied test CA. The stack was stopped after validation, preserving its volume. Browser trust was declined; two-device media reachability remains unverified. The optional GPU configuration was only validated offline: no GPU image layers or model weights were downloaded and no GPU was started. Remote model hosting, public media/TURN reachability, regional routing, external retention settings and long-running production behavior remain deployment checks.

The application is a runnable development project with a tested translation architecture and experimental local anti-spoof screening. It is not a claim of production certification, universal language accuracy, verified data residency or a validated security detector.

## Provider credit controls and developer journal

The current revision adds persistent, atomic daily usage reservations before live provider requests; bounded admission/concurrency and reconnect attempts; terminal authentication/quota handling; and a 15-minute default live room lifetime. Mocked tests cover restart persistence, UTC rollover, concurrent caps, zero limits, unavailable storage, idle STT termination, same-language recognition bypass, and eligibility rechecks after queued admission. A queued branch whose speaker expires or last listener leaves reserves no credit and makes no upstream request. These tests do not call a real provider.

The three-speaker synthetic WebRTC regression was repeated after these transport changes and passed all six directed branches and recipient checks. The installed local development server emitted compatibility/fallback and shutdown warnings; the transport assertions passed. No paid Gnani, hosted Evon or LiveKit Cloud calls were used.

Browser review checked the journal's root-cause search and expandable evidence, mobile navigation, offline unknown usage, and the local demo summary. Reading the demo summary returned seven zero-usage resources and created no SQLite ledger. The normal production frontend build passed. The source-maintained journal distinguishes fixed behavior from pending real-provider and deployment checks.

Application reservations are not a provider invoice or a remaining-balance reading. Provider-side billing controls remain necessary for LiveKit participant time/bandwidth, idle GPU compute and usage from other applications. See [CREDIT_CONTROLS.md](CREDIT_CONTROLS.md).

## Self-host deployment preparation

The added backend checks cover redacted readiness, secure public endpoints, explicit frontend origins, self-generated signing credentials and safe validation failures. At the 24 October preparation checkpoint, 195 backend tests and 79 frontend tests passed; the current totals are listed above. The frontend checks include seven deployment-report and read-only request checks. Normal production and explicitly scripted preview builds are checked separately.

The offline generator prepares a Linux host-network stack for the frontend, one API/RTC worker, LiveKit and Caddy's shared HTTPS/TURN port. Unit checks cover credential generation, overwrite refusal, supported bounds, literal secret handling, topology consistency, no-network preparation, tamper detection and failure redaction. POSIX permissions and symbolic-link checks require their Linux run; Windows skips are not evidence that Linux permissions have been exercised.

Docker Compose configuration validation passed with synthetic inputs without starting containers. Shell syntax was checked; this does not establish successful Linux startup. Real containers, certificates, public UDP and TURN fallback still require the intended server. No Gnani, hosted Evon, LiveKit Cloud or other paid inference calls were made during preparation.

The API image installs the exact runtime dependency pins and artifact hashes exported from `server/uv.lock`, instead of resolving floating ranges during image construction. Installation of the Linux wheels and `pip check` passed in the local Docker API image on 28 October. The production host, production generator's POSIX permissions and public media still need their own acceptance; Windows checks do not establish those properties.

Browser review verified the separate Deployment setup page on desktop and mobile, manual refresh against the local demo API, and unknown statuses after that API was stopped. The page contains no credential inputs. The frontend uses system fonts without an external font stylesheet. The developer journal retains deployment acceptance as pending despite the completed configuration work.

## Permission and account reporting preparation

At the 24 October preparation checkpoint, the backend suite passed **195 tests**, including 37 approval/rate/privacy checks and 25 prepared Gnani-runner checks using provider doubles. The frontend passed **79 tests**, including 30 usage-report validation checks. Current regression totals are listed above. The actual Windows `--plan` command was exercised without loading provider clients or making requests; its Hindi output is ASCII-safe JSON on older console encodings.

Default live provider reservations require an explicit bounded operator grant. The same transaction checks daily caps and per-flow budgets. Tests cover expiry, replacement, atomic contention, cancellation, timeouts, missing consent, no automatic retries and redacted reports. The standard and cloned checks remain separate. No actual Gnani entitlement, voice-clone quality or provider invoice has been validated during this preparation.

Browser review of the local loopback API displayed the owner's manually reported INR balance and supplied pricing table, with a locked flow and seven zero-usage counters. Desktop/mobile layouts, pause and refresh were checked; the API key was absent from rendered page text. No balance is baked into the frontend source. Public API responses hide manual financial evidence by default, and the static preview keeps account amounts unknown.

## First approved Gnani speech check

On 24 October 2026, the owner approved one specific TTS→STT flow. Gnani synthesized the fixed Hindi phrase “नमस्ते भारत।” and the streaming recognizer returned the identical phrase. The grant closed after the check; no automatic retry, enrollment, clone synthesis, translation or LiveKit Cloud call occurred.

| Measurement | Observed value | Boundary |
| --- | ---: | --- |
| Synthesis requests / input | 1 / 12 characters | Reserved before the single request |
| First PCM | 505.91 ms | Synthesis-stage start to first received PCM |
| Full synthesis | 1640.93 ms | Synthesis-stage start to completed PCM stream |
| Generated audio | 1.12 seconds | 16 kHz mono PCM sample count |
| Recognition | 1 connection / 4 reserved seconds | Conservative connected-time reservations |
| STT final | 2081.17 ms | Connection plus streamed test audio to first final transcript |

The spoken phrase matched in this one check. These measurements do not certify general accuracy, ear-to-ear meeting delay, a latency percentile or cloned-voice similarity. The separate Usage flow record contains these actual measurements and counters. The owner reported observing a charge deduction; its exact amount was not supplied. Reference arithmetic remains separate from a verified invoice or programme-credit conversion.
