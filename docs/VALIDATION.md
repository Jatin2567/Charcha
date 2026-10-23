# Verification and remaining live checks

Verified on 24 October 2026, on the local Windows development environment.

| Area                                        | Result           | What this establishes                                                                                                                                                           |
| ------------------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python API/provider/lifecycle suite         | 53 passing tests | Room isolation, consent, bounded queues, expiration, cancellation, voice validation, mocked provider protocols and WebSocket header authentication                              |
| Frontend suite                              | 23 passing tests | Routing filters, scripted examples, transcript reconciliation/recovery and PCM WAV encoding                                                                                     |
| TypeScript and Vite production build        | Passed           | The application compiles and produces a deployable static frontend                                                                                                              |
| Real local WebRTC, three distinct languages | Passed           | Three synthetic PCM publishers; six directed provider-double branches; two non-silent appropriate tracks per listener; no self/original/wrong-language subscriptions            |
| Same-language transport experiment          | Passed           | Hindi/Hindi/Tamil forwarding and resampling, shared target language generation, mute/unmute and expiry gates using synthetic PCM and provider doubles                           |
| Browser acceptance journey                  | Passed           | Create, language selection, consent, join, six scripted shared turns, translated/original views, understanding confirmation, reconnect snapshot, leave, recap and explicit save |
| Responsive meeting                          | Checked          | Mobile participant stage scrolls; essential controls remain accessible; transcript panel can be closed                                                                          |

The real RTC checks do **not** call Gnani or Evon. Their synthetic test audio is only a transport fixture. None of these results establishes actual translation accuracy, voice-clone similarity, end-to-end listener latency or external provider account access.

## Still requires your accounts/infrastructure

1. Configure Gnani STT/TTS/voice-cloning access, a LiveKit deployment and a served Evon endpoint.
2. Verify both directions with actual Hindi and Tamil speakers, then Bengali fan-out.
3. Check voice/model IDs, quotas, streaming permissions, reference quality and cross-language cloning on the account being used.
4. Collect actual latency and cost under the intended network and speech concurrency. The UI's server timing boundary is distinct from audible receiver playback.
5. Obtain bilingual review of the synthetic evaluation scripts and then review actual recorded outputs. Draft gold text is not certified ground truth.

## Deployment limits

Docker configuration is included, but no image/container acceptance run was possible because the local Docker daemon was not running. The optional GPU Evon profile was not started and no large model was downloaded. Remote model hosting, HTTPS/WSS, media reachability, regional routing, external retention settings and long-running production behavior remain deployment checks.

The application is a runnable development project with a tested translation architecture. It is not a claim of production certification, universal language accuracy, verified data residency or a security detector.
