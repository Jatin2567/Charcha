# Verification and remaining live checks

Verified on 24 October 2026, on the local Windows development environment.

| Area                                        | Result            | What this establishes                                                                                                                                                                                         |
| ------------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python API/provider/lifecycle suite         | 130 passing tests | Room isolation, consent, bounded queues, expiration, cancellation, voice validation, mocked provider protocols, WebSocket header authentication and per-branch performance reporting                          |
| Frontend suite                              | 64 passing tests  | Routing, transcript recovery, WAV encoding, timing summaries, filters, sanitized exports, browser-stat conversion and report-tab isolation                                                                    |
| TypeScript and Vite production build        | Passed            | The application compiles and produces a deployable static frontend                                                                                                                                            |
| Real local WebRTC, three distinct languages | Passed            | Three synthetic PCM publishers; six directed provider-double branches; two non-silent appropriate tracks per listener; no self/original/wrong-language subscriptions                                          |
| Same-language transport experiment          | Passed            | Hindi/Hindi/Tamil forwarding and resampling, shared target language generation, mute/unmute and expiry gates using synthetic PCM and provider doubles                                                         |
| Browser acceptance journey                  | Passed            | Create, language selection, consent, join, six scripted shared turns, translated/original views, understanding confirmation, reconnect snapshot, leave, recap and explicit save                               |
| Responsive meeting                          | Checked           | Mobile participant stage scrolls; essential controls remain accessible; transcript panel can be closed                                                                                                        |
| Performance & readiness browser journey     | Passed            | Separate report tab retains room access while the call stays connected; 14 scripted branch rows remain excluded from live percentiles; language filtering, setup scrolling and filtered JSON download checked |
| Responsive performance page                 | Checked           | Mobile page width stays within its viewport; wide tables scroll independently; desktop summary grid and setup reference reviewed                                                                              |

The real RTC checks do **not** call Gnani or Evon. Their synthetic test audio is only a transport fixture. None of these results establishes actual translation accuracy, voice-clone similarity, end-to-end listener latency or external provider account access.

Performance reporting retains at most 1,000 terminal branches per room. Automated checks cover exact-room authorization, configuration redaction, missing STT markers, exclusion of simulated/forwarded/failed/cancelled branches, queue cancellation, partial failure and first-PCM timing distinct from playout completion. Typed same-language cloning bypasses MT and keeps embeddings out of reports. Browser network-stat conversion is checked with standard-shaped fixtures; its real-device collection still needs the live call check. The STT timer is receipt of a processing event to receipt of a transcript, not a measured speech-end boundary. See [GO_LIVE.md](GO_LIVE.md) for exact definitions and required inputs.

## Still requires your accounts/infrastructure

1. Configure Gnani STT/TTS/voice-cloning access, a LiveKit deployment and a served Evon endpoint.
2. Verify both directions with actual Hindi and Tamil speakers, then Bengali fan-out.
3. Check voice/model IDs, quotas, streaming permissions, reference quality and cross-language cloning on the account being used.
4. Collect actual latency and cost under the intended network and speech concurrency. The UI's server timing boundary is distinct from audible receiver playback.
5. Obtain bilingual review of the synthetic evaluation scripts and then review actual recorded outputs. Draft gold text is not certified ground truth.

## Deployment limits

Docker configuration is included, but no image/container acceptance run was possible because the local Docker daemon was not running. The optional GPU Evon profile was not started and no large model was downloaded. Remote model hosting, HTTPS/WSS, media reachability, regional routing, external retention settings and long-running production behavior remain deployment checks.

The application is a runnable development project with a tested translation architecture. It is not a claim of production certification, universal language accuracy, verified data residency or a security detector.

## Provider credit controls and developer journal

The current revision adds persistent, atomic daily usage reservations before live provider requests; bounded admission/concurrency and reconnect attempts; terminal authentication/quota handling; and a 15-minute default live room lifetime. Mocked tests cover restart persistence, UTC rollover, concurrent caps, zero limits, unavailable storage, idle STT termination, same-language recognition bypass, and eligibility rechecks after queued admission. A queued branch whose speaker expires or last listener leaves reserves no credit and makes no upstream request. These tests do not call a real provider.

The three-speaker synthetic WebRTC regression was repeated after these transport changes and passed all six directed branches and recipient checks. The installed local development server emitted compatibility/fallback and shutdown warnings; the transport assertions passed. No paid Gnani, hosted Evon or LiveKit Cloud calls were used.

Browser review checked the journal's root-cause search and expandable evidence, mobile navigation, offline unknown usage, and the local demo summary. Reading the demo summary returned seven zero-usage resources and created no SQLite ledger. The normal production frontend build passed. The source-maintained journal distinguishes fixed behavior from pending real-provider and deployment checks.

Application reservations are not a provider invoice or a remaining-balance reading. Provider-side billing controls remain necessary for LiveKit participant time/bandwidth, idle GPU compute and usage from other applications. See [CREDIT_CONTROLS.md](CREDIT_CONTROLS.md).

## Self-host deployment preparation

The added backend checks cover redacted readiness, secure public endpoints, explicit frontend origins, self-generated signing credentials and safe validation failures. All 130 backend tests and 64 frontend tests pass. The frontend tests include seven deployment-report and read-only request checks. Both the normal production build and explicitly scripted preview are checked separately.

The offline generator prepares a Linux host-network stack for the frontend, one API/RTC worker, LiveKit and Caddy's shared HTTPS/TURN port. Unit checks cover credential generation, overwrite refusal, supported bounds, literal secret handling, topology consistency, no-network preparation, tamper detection and failure redaction. POSIX permissions and symbolic-link checks require their Linux run; Windows skips are not evidence that Linux permissions have been exercised.

Docker Compose configuration validation passed with synthetic inputs without starting containers. Shell syntax was checked; this does not establish successful Linux startup. Real containers, certificates, public UDP and TURN fallback still require the intended server. No Gnani, hosted Evon, LiveKit Cloud or other paid inference calls were made during preparation.

The API image now installs the exact runtime dependency pins and artifact hashes exported offline from `server/uv.lock`, instead of resolving floating ranges during image construction. This validates the lock export, not installation of every Linux wheel; the Docker build still requires the deployment host. The offline generator suite passes 20 tests, with two POSIX-specific checks skipped on Windows.

Browser review verified the separate Deployment setup page on desktop and mobile, manual refresh against the local demo API, and unknown statuses after that API was stopped. The page contains no credential inputs. The frontend uses system fonts without an external font stylesheet. The developer journal retains deployment acceptance as pending despite the completed configuration work.
