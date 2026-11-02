export type JournalStatus = 'fixed' | 'improved' | 'pending';
export type JournalArea =
  | 'audio'
  | 'reliability'
  | 'security'
  | 'measurement'
  | 'experience'
  | 'usage'
  | 'delivery';
export type JournalEvidence =
  | 'automated'
  | 'synthetic-rtc'
  | 'browser'
  | 'review'
  | 'live-provider'
  | 'live-pending';
export interface DeveloperJournalEntry {
  id: string;
  date: string;
  status: JournalStatus;
  area: JournalArea;
  title: string;
  summary: string;
  cause: string;
  change: string;
  verification: string;
  evidence: JournalEvidence[];
  references: string[];
  outstanding?: string;
}
export interface JournalFilter {
  status: JournalStatus | 'all';
  area: JournalArea | 'all';
  search: string;
}
export const JOURNAL_UPDATED = '2026-10-31';
export const JOURNAL_STATUS_LABELS: Record<JournalStatus, string> = {
  fixed: 'Fixed',
  improved: 'Improved',
  pending: 'Pending',
};
export const JOURNAL_AREA_LABELS: Record<JournalArea, string> = {
  audio: 'Audio & routing',
  reliability: 'Reliability',
  security: 'Privacy & access',
  measurement: 'Measurement',
  experience: 'Experience',
  usage: 'Provider usage',
  delivery: 'Live delivery',
};
export const JOURNAL_EVIDENCE_LABELS: Record<JournalEvidence, string> = {
  automated: 'Automated check',
  'synthetic-rtc': 'Synthetic WebRTC',
  browser: 'Browser check',
  review: 'Code review',
  'live-provider': 'Approved API check',
  'live-pending': 'Live check pending',
};
export const DEFAULT_JOURNAL_FILTER: JournalFilter = {
  status: 'all',
  area: 'all',
  search: '',
};

// Curated engineering notes, not generated room activity. Update only with evidence.
export const developerJournal: DeveloperJournalEntry[] = [
  {
    id: 'docker-https-gpu-preparation',
    date: '2026-10-28',
    status: 'improved',
    area: 'delivery',
    title: 'Local containers build and secure network setup is prepared',
    summary:
      'The API and frontend build in Docker, the four-service local stack starts, and HTTPS health passes with the supplied test certificate. Browser trust was deferred by the owner.',
    cause:
      'Earlier checks could not reach the Docker engine. A second device also needs certificate trust and restricted network access. The old optional GPU profile used an unpinned model and serving image. A screening test also compared tone-start time with a decoder window that already contained startup silence.',
    change:
      'Added short-lived local certificate generation with private file permissions and a discarded signing key, a device-specific firewall preparation script, and a bounded HTTPS/audio acceptance probe. Evon now has immutable metadata-verified model and runtime pins, authenticated loopback serving, and an offline host/stop-plan checker. Removed the obsolete GPU profile.',
    verification:
      'Docker builds, dependency checks, HTTPS frontend/API and two WSS signaling joins passed. Local WebRTC routing and CPU screening fixtures passed without providers. The corrected enforcement test checks all 64,600 samples and the allow verdict before releasing audio; production enforcement was unchanged. Detailed results are in docs/VALIDATION.md. GPU runtime compatibility remains untested.',
    evidence: ['automated', 'synthetic-rtc', 'review', 'live-pending'],
    references: [
      'scripts/create_lan_certificate.py',
      'scripts/configure_lan_firewall.ps1',
      'scripts/verify_lan_stack.py',
      'scripts/verify_screening_transport.py',
      'scripts/evon_host_preflight.py',
      'deploy/evon/inputs.verified-2026-10-28.json',
      'docs/VALIDATION.md',
    ],
    outstanding:
      'Windows certificate trust was declined and remains unchanged. The second device still needs certificate trust, its exact LAN address, firewall setup and a listening test. GPU execution, real translation, labelled detector evaluation and voice cloning remain later work.',
  },
  {
    id: 'pre-gpu-local-readiness',
    date: '2026-10-31',
    status: 'improved',
    area: 'reliability',
    title: 'Five languages reached a second RTC participant with standard voices',
    summary:
      'Nine of ten directions delivered translated audio. Bengali → Marathi stopped during local setup before any provider reservation. All five languages worked as both source and target. On the Marathi clip the published year was 1976, while Prisma returned 1972 in both routes. The results page flags that error separately from audio delivery.',
    cause:
      'The CLI login expired, the image needed its existing interpreter exposed as python, and serialized functions needed matching local Python 3.12. The first Xet transfer stalled. Initial Hindi→Tamil text echoed the input. Tamil STT returned no final in the first speech flow. Its successful follow-up does not establish the original failure’s cause or confirm the provider-served STT model.',
    change:
      'Prompt v3 handles code-switches and identifiers. Public readings pass through Prisma, Evon and Timbre between two RTC peers. A Windows file sharing conflict can block receipt replacement, so the runner now retries only local writes. Twenty direction-specific manual checklists are available.',
    verification:
      'Nine STT connections, nine translations, nine standard TTS requests, 106 STT seconds and 867 TTS characters. The Gnani reference is ₹3.1359. The Modal app stopped, with a $0.60 workspace meter increase and $0 billed at the snapshot. A separate simultaneous transport test timed out in one process, then delivered all 25 expected recipient routes with six isolated peers and provider doubles.',
    evidence: ['automated', 'review', 'live-provider', 'live-pending'],
    references: [
      'scripts/evon_benchmark.py',
      'scripts/verify_group_conference.py',
      'scripts/run_five_language_calls.py',
      'web/src/data/fiveLanguageStageResults.json',
      'scripts/modal_evon.py',
      'scripts/modal_evon_runtime.py',
      'scripts/check_hindi_tamil_e2e.py',
      'scripts/import_hindi_tamil_evidence.py',
      'web/src/components/HindiTamilProviderEvidence.tsx',
      'scripts/check_tamil_hindi_followup.py',
      'scripts/import_tamil_hindi_followup_evidence.py',
      'web/src/components/TamilHindiFollowupEvidence.tsx',
      'scripts/setup_modal.ps1',
      'docs/MODAL_TESTING.md',
      'scripts/plan_five_language_test.py',
      'docs/FIVE_LANGUAGE_TESTING.md',
      'docs/FIVE_LANGUAGE_SCREENING.md',
      'scripts/evon_prepare.py',
      'scripts/prepare_lan_test.py',
      'server/artha_mesh/providers/evon.py',
      'evaluation/audio_screening.py',
      'web/src/components/LatencyGroups.tsx',
      'docs/GPU_TESTING.md',
      'docs/TWO_DEVICE_TESTING.md',
      'docs/VALIDATION.md',
    ],
    outstanding:
      'Further paid tests need new approval. Investigate the initial Tamil failure and repeat timings before attributing improvement to a model or timeout setting. Bilingual meaning review, real-device camera/listening, five-language provider capacity and listener latency remain unverified. GCP hosting is conditional on need; screening and cloning stay deferred. Reconcile actual charges separately from local reference prices.',
  },
  {
    id: 'cold-start-audio',
    date: '2026-10-28',
    status: 'fixed',
    area: 'audio',
    title: 'Original audio no longer waits behind the leading zero-frame backlog',
    summary:
      'Three matched local runs before and after the repair reduced median source-capture to received PCM from 686.500 ms to 210.535 ms. The old multi-second incident stays separate from this comparison.',
    cause:
      'A new decoder can emit all-zero PCM before the source captures sound. Replaying those leading queued frames at real-time pace delayed the first signal; raw output also used a synthesis-sized 250 ms queue.',
    change:
      'Output negotiation still starts immediately, but forwarding drops only leading exact-zero frames. Every nonzero sample, including very quiet input, and pauses after speech begins are preserved. Raw output uses a 60 ms queue; synthesis keeps 250 ms. Subscriber, recipient, screening and mute checks remain. Performance now shows fresh before/after evidence separately from the prior incident.',
    verification:
      'All three baseline and three repaired RTC runs passed routing, mute, receiver detach and unmute. Six directions per group gave ranges of 322.65–1,149.82 ms before and 172.18–379.97 ms after, with a 69.3% lower observed median. First-run agent-input to first relay PCM submission fell from 886.18 ms to 35.04 ms. A separate real-model monitor fixture received PCM at 158.74 ms and used 566.684 ms compute after a 4,037.5 ms window. The full suites passed 348 backend and 129 frontend tests, including six new audio and five comparison cases; the production build passed. No provider requests were used.',
    evidence: ['automated', 'synthetic-rtc', 'browser', 'review', 'live-pending'],
    references: [
      'server/artha_mesh/transport/livekit.py',
      'server/tests/test_cold_start_audio.py',
      'scripts/verify_transport.py',
      'web/src/components/ColdStartComparison.tsx',
      'web/src/data/coldStartResults.json',
      'docs/VALIDATION.md',
    ],
    outstanding:
      'The prior 12,132.83 / 4,669.78 ms incident had different host load and is excluded from the improvement calculation. Repeat real-device and loaded monitoring measurements; synthetic PCM does not measure acoustic playback or translation. Voice cloning remains deferred.',
  },
  {
    id: 'local-audio-screening-lab',
    date: '2026-10-31',
    status: 'improved',
    area: 'measurement',
    title: 'Live VoiceShield audio monitoring and experimental screening evidence',
    summary:
      'A local FLEURS pilot tested ten human recordings in each of five languages. The full-window detector falsely flagged 14 of 50 and returned 12 unknowns, so monitor mode is recommended. The native 4,037.5 ms input stays intact; earlier matched diagnostics reduced CPU analysis from 403.500 to 268.460 ms.',
    cause:
      'Most of the first-verdict wait is audio collection. Public human speech exposed domain/operating-point failures that tones could not reveal. Tamil TSV quotation marks also required literal-tab parsing. Short-prefix agreement on synthetic signals did not establish reliable human performance.',
    change:
      'VoiceShield now displays real local AASIST waveform assessments from the room stream. Microphone participants receive live signal badges, an acoustic warning banner and a review dialog with measured scores. The panel reports model readiness, per-window compute and queue times, thresholds and exportable observations. A dedicated dev:shield launcher enables monitor mode with provider access disabled. Muted, departed and disconnected participants cannot retain active warnings. Performance and Audio lab retain the earlier public-speech evaluation.',
    verification:
      'The earlier human-speech pilot recorded 24 allowed, 14 false alarms and 12 unknowns among 50 readings. On October 31, the installed ONNX classifier processed diagnostic tones through real local WebRTC. Audio arrived before a model window completed, and all monitoring actions stayed observed. A 30-second generated-tone source produced actual browser badges, a warning banner and a review dialog, with zero provider-usage delta; muting cleared its latest result. These functional checks establish execution and event delivery. Speech detection accuracy and physical playback impact remain unverified.',
    evidence: ['automated', 'synthetic-rtc', 'browser', 'review', 'live-pending'],
    references: [
      'web/src/pages/AudioLab.tsx',
      'web/src/services/audioLab.test.ts',
      'web/src/components/LocalDiagnostics.tsx',
      'web/src/components/VoiceShieldPanel.tsx',
      'web/src/components/VoiceShieldPanel.test.ts',
      'web/src/services/voiceShield.ts',
      'web/src/services/localDiagnostics.test.ts',
      'server/artha_mesh/services/audio_screening.py',
      'scripts/verify_audio_screening.py',
      'scripts/benchmark_screening_compute.py',
      'scripts/compare_screening_durations.py',
      'scripts/prepare_speech_screening_kit.py',
      'scripts/run_speech_screening_study.py',
      'scripts/prepare_public_human_speech.py',
      'scripts/evaluate_public_human_speech.py',
      'web/src/components/PublicSpeechScreeningResults.tsx',
      'docs/PUBLIC_HUMAN_SCREENING.md',
      'docs/REAL_SPEECH_TEST_KIT.md',
      'docs/SCREENING_LATENCY.md',
      'docs/VALIDATION.md',
    ],
    outstanding:
      'Investigate the failed human baseline and collect independently labelled synthetic clips plus real-microphone coverage. FLEURS supplies no speaker IDs; speaker independence is unknown. Use separate data for future calibration. Automatic blocking and shortened-input release are not validated; cloning stays deferred.',
  },
  {
    id: 'local-browser-ice',
    date: '2026-10-30',
    status: 'improved',
    area: 'audio',
    title: 'Conference controls now recover without reopening capture',
    summary:
      'Normal conferencing now has a dedicated launcher, room readiness, deliberate microphone and camera capture, device selection and speaker recovery. Original-audio rehearsal and approved standard-voice interpretation have separate launch profiles. Ten language choices are available; latency research, screening and cloning remain later work.',
    cause:
      'The earlier media implementation could reacquire a default device after hardware ended, race a late mute against a fresh unmute, or leave playback failures unclear. Private canary setup also obscured the ordinary call workflow. Camera-only permissions and source-audio isolation still needed to hold through recovery.',
    change:
      'Added server-authoritative, read-only readiness and new-source allowance checks; explicit microphone authorization before capture; rollback for failed or stale requests; and capture-off reconnect/device-loss handling. Speaker unlock and output switching are recoverable. The normal live launcher keeps per-flow permission, zero recognition retries and no enrollment; its frontend receives no provider secrets. Camera-only peer video and interpreter-only source audio remain isolated.',
    verification:
      'Six launcher checks passed. Browser checks joined two muted participants through normal invitations, reconnected with capture off and left without saving a recap. A live-mode Hindi/Tamil pair displayed operator approval and disabled unmute. The final six-peer sequential RTC regression passed 20 synthetic translation branches, 25 first-audible routes and five camera receivers in 122.793 seconds with no structured cleanup failures. Runtime is a fixture duration, not speech latency. The late SDK closed-publisher shutdown warning remains preserved. No provider API or paid server was used.',
    evidence: ['automated', 'browser', 'synthetic-rtc', 'live-pending'],
    references: [
      'scripts/local.mjs',
      'scripts/conference_runtime.mjs',
      'scripts/test_conference_runtime.mjs',
      'scripts/verify_transport.py',
      'scripts/check_browser_audio.py',
      'scripts/verify_five_language_routing.py',
      'web/src/services/meetingVideo.ts',
      'web/src/services/meetingMicrophone.ts',
      'web/src/services/localMediaCapture.ts',
      'web/src/hooks/useConferenceReadiness.ts',
      'web/src/services/cameraPreview.ts',
      'web/src/components/CameraVideo.tsx',
      'server/tests/test_conference_transport.py',
      'server/tests/test_five_language_rtc_diagnostics.py',
      'server/artha_mesh/transport/livekit.py',
      'server/tests/test_conference_readiness.py',
      'docs/LIVE_CONFERENCING.md',
      'docs/LOCAL_TESTING.md',
    ],
    outstanding:
      'Complete human microphone/camera checks in Chrome/Incognito and on two devices, sustained playback, simultaneous-speaking capacity and approved real-provider meaning review. First decoded synthetic sound does not establish these. Five active live sources need reviewed admission limits. Investigate the retained late-close warning. Latency optimization, deepfake detection and voice cloning are deferred features.',
  },
  {
    id: 'local-transport-test-lab',
    date: '2026-10-30',
    status: 'improved',
    area: 'experience',
    title: 'Device rehearsal now has clear invitations and manual reliability scripts',
    summary:
      'Invitations explain whether they work on the same computer or need secure device setup. Call status separates configuration, model verification and approval limits. A new original-audio stage supplies six manual two-device reliability scripts without speech API calls.',
    cause:
      'A copied localhost link looked shareable across devices, and one approval message covered several different blocked states. The previous second-device stage assumed live translation, leaving no dedicated free device-reliability checklist.',
    change:
      'Added invitation scope guidance before copying local/HTTP links, expandable read-only call setup and allowance details, and distinct configuration/expired/exhausted states. Approval time uses the server snapshot and elapsed browser time; no model is probed or flow renewed. Six free device scripts use manual save/export. Later research is collapsed. A toast timer now follows the message instead of restarting on every call-clock render, so temporary notices can clear.',
    verification:
      'All 258 frontend tests passed, including invitation scope, guarded room status, clock-based expiry, unknown versus zero resource amounts and manual observation storage. Browser checks verified invitation guidance before copy and connected original-audio details, then saved and cleared a temporary Blocked device observation without claiming a listening pass. No speech-provider request, model probe, paid server or approval grant was made. Human two-device results remain pending.',
    evidence: ['automated', 'synthetic-rtc', 'browser', 'live-pending'],
    references: [
      'web/src/pages/TestLab.tsx',
      'web/src/services/testLab.ts',
      'web/src/services/invitation.ts',
      'web/src/components/InvitationHelp.tsx',
      'web/src/components/ConferenceAllowance.tsx',
      'web/src/services/conferencePresentation.ts',
      'docs/TWO_DEVICE_TESTING.md',
      'server/tests/test_transport_only.py',
      'scripts/verify_transport.py',
      'docs/TEST_FLOWS.md',
      'scripts/plan_language_matrix.py',
      'docs/LANGUAGE_TEST_MATRIX.md',
      'docs/EVON_ACCESS_GUIDE.md',
    ],
    outstanding:
      'Complete trusted HTTPS setup and actual two-device listening/camera checks. Then obtain a bounded approval for live translation meaning review. Attendance history and synchronized hand raising remain possible later improvements; voice cloning stays deferred.',
  },
  {
    id: 'mute-state',
    date: '2026-10-24',
    status: 'fixed',
    area: 'audio',
    title: 'Mute state now follows the server',
    summary:
      'A failed mute update can no longer leave the microphone sending while the interface appears muted.',
    cause:
      'Browser media changes and the room update can finish at different times; a rejected update leaves their states inconsistent.',
    change:
      'The server participant state is authoritative. A failed update mutes the local audio path, disconnecting if muting fails; stale asynchronous operations cannot restore it. Production retains unpublish-on-mute. The Python RTC receiver harness now bounds queued PCM and handles TrackUnsubscribed, so stale received samples cannot masquerade as post-mute transmission.',
    verification:
      'The final two-peer synthetic RTC check verified server output removal, receiver detachment within five seconds, no new PCM while muted and restored audio within six seconds after unmute. Observed mute-to-detach was 256.57 ms. Sixteen focused transport/screening/probe tests also passed. Cold-start first-audio remained slow and is tracked separately.',
    evidence: ['automated', 'synthetic-rtc'],
    references: [
      'web/src/hooks/useMeetingAudio.ts',
      'server/artha_mesh/transport/livekit.py',
      'scripts/verify_same_language.py',
    ],
    outstanding: 'Repeat permission, network-failure and mute checks on the intended live devices.',
  },
  {
    id: 'late-microphone-permission',
    date: '2026-10-24',
    status: 'fixed',
    area: 'reliability',
    title: 'Late microphone permission no longer leaves a stream open',
    summary:
      'Closing a device test or enrollment while permission is pending safely releases any stream that arrives later.',
    cause:
      'The permission promise can resolve after its screen closes, when ordinary component cleanup has already run.',
    change:
      'Generation and lifecycle guards stop late streams. Enrollment recording also has a bounded duration and releases recording and decoding resources.',
    verification:
      'WAV encoding checks cover the recorded format and duration. Lifecycle guards were reviewed for cleanup after late completion; automated permission-prompt race coverage is not claimed.',
    evidence: ['automated', 'review'],
    references: [
      'web/src/hooks/useDevices.ts',
      'web/src/hooks/useVoiceRecorder.ts',
      'web/src/hooks/useVoiceRecorder.test.ts',
    ],
    outstanding:
      'Browser permission prompts vary; repeat denial and delayed approval on the deployment browsers.',
  },
  {
    id: 'translated-track-isolation',
    date: '2026-10-24',
    status: 'improved',
    area: 'audio',
    title: 'Each listener receives the intended translated tracks',
    summary:
      'Track permissions and subscriptions enforce the language routing matrix and prevent self echo.',
    cause:
      'Default automatic subscriptions would let listeners receive source audio or tracks intended for another language.',
    change:
      'Human source tracks are available to the agent. Output permissions identify recipients explicitly, and browser subscriptions validate the agent, source speaker and target language.',
    verification:
      'Three real local RTC publishers with synthetic PCM produced all six directed routes. Listeners received two appropriate non-silent tracks, with no self, original or wrong-language subscription.',
    evidence: ['automated', 'synthetic-rtc'],
    references: [
      'web/src/services/livekit.ts',
      'server/artha_mesh/services/routing.py',
      'server/artha_mesh/transport/livekit.py',
      'scripts/verify_routing.py',
    ],
    outstanding:
      'The providers in that experiment were test doubles; actual translations and real network behavior still need listening checks.',
  },
  {
    id: 'forwarding-playout',
    date: '2026-10-30',
    status: 'fixed',
    area: 'audio',
    title: 'First synthesized PCM no longer waits for a later provider chunk',
    summary:
      'A valid short first synthesis chunk now reaches the output without waiting to fill the usual 20 ms batch. Earlier same-language resampling and synthesis ownership fixes remain in place.',
    cause:
      'The output batcher could hold a valid short first PCM chunk until a later provider chunk arrived. That added the inter-chunk gap before dispatch. Earlier forwarding also needed sample-rate conversion and a pause while synthesized speech owned its output.',
    change:
      'Dispatch the first complete PCM samples immediately, then retain ordinary batching. Preserve odd-byte carry, sample order, cancellation cleanup and output ownership. Forwarded PCM remains resampled and pauses while synthesis owns the track. This production-path correction is separate from the synthetic harness shutdown repair.',
    verification:
      'Short-first-PCM regression checks cover 16/24 kHz, delayed next chunks, odd-byte carry and cancellation. In a mocked 125 ms provider-gap experiment, median dispatch wait fell from 135.372 ms to 0.124 ms. This is a controlled local result, not a measured Gnani improvement. Earlier Hindi/Hindi/Tamil synthetic RTC checks covered forwarding, output, mute/unmute and expiry.',
    evidence: ['synthetic-rtc', 'automated'],
    references: ['server/artha_mesh/transport/livekit.py', 'scripts/verify_same_language.py', 'server/tests/test_streaming_first_pcm.py'],
    outstanding:
      'Measure the changed first-chunk path with approved real-provider speech and physical listener output. Saved paid timing records are unchanged; listening quality and real-world latency improvement remain unverified.',
  },
  {
    id: 'snapshot-recovery',
    date: '2026-10-24',
    status: 'fixed',
    area: 'reliability',
    title: 'Reconnection replaces stale room state',
    summary:
      'The room snapshot restores the roster, transcript and measurements without retaining stale processing indicators.',
    cause:
      'Incrementally merging a fresh snapshot into old state can keep finished stages, errors or a running sample indicator visible.',
    change:
      'Snapshot handling replaces authoritative state and clears transient stage and error state. Demo completion also releases its running indicator.',
    verification:
      'Reducer and recovery checks cover the replacement behavior. The browser journey refreshed an active scripted room and recovered its transcript.',
    evidence: ['automated', 'browser'],
    references: [
      'web/src/state/roomReducer.ts',
      'web/src/state/roomReducer.test.ts',
      'web/src/state/recovery.test.ts',
    ],
    outstanding:
      'Verify interruption and recovery with real provider streams and the target network.',
  },
  {
    id: 'websocket-authentication',
    date: '2026-10-24',
    status: 'improved',
    area: 'security',
    title: 'Browser event authentication stays out of the URL',
    summary:
      'The browser sends its scoped event credential in the WebSocket upgrade protocol rather than a query string.',
    cause: 'Credentials in URLs can be retained by URL-oriented logs and copied links.',
    change:
      'The browser and API use a matched upgrade protocol, exact-room authorization and origin checks. Compatibility handling for older query-token clients is excluded from access logs.',
    verification:
      'Backend tests cover authenticated upgrades, invalid credentials and room scope. The implementation was reviewed alongside the documented contract.',
    evidence: ['automated', 'review'],
    references: ['web/src/hooks/useRoomEvents.ts', 'server/artha_mesh/main.py', 'docs/CONTRACT.md'],
    outstanding:
      'Check reverse-proxy header forwarding, HTTPS/WSS and operational logging on the deployment host.',
  },
  {
    id: 'honest-timing-boundaries',
    date: '2026-10-24',
    status: 'fixed',
    area: 'measurement',
    title: 'Missing timing markers remain unavailable',
    summary: 'The performance page separates measured server delay from unmeasured listener delay.',
    cause:
      'An absent STT processing event cannot establish zero delay. Demo rows, forwarding and failures also cannot establish successful translation percentiles.',
    change:
      'Missing STT markers remain null. p50/p95 include only completed live first-PCM branches; simulated, forwarded, failed and cancelled branches remain separately visible.',
    verification:
      'Backend and frontend checks cover missing markers, nearest-rank percentiles, branch failures, first PCM versus playout completion, and exclusions.',
    evidence: ['automated'],
    references: [
      'server/artha_mesh/services/pipeline.py',
      'web/src/services/performance.ts',
      'web/src/services/performance.test.ts',
      'docs/GO_LIVE.md',
    ],
    outstanding:
      'Collect real microphone samples. The server boundary does not include all microphone buffering or receiver playback.',
  },
  {
    id: 'bounded-measurement-exports',
    date: '2026-10-24',
    status: 'improved',
    area: 'measurement',
    title: 'Performance history is bounded and exports contain technical metadata',
    summary: 'Room measurement history retains at most 1,000 terminal language-branch rows.',
    cause:
      'An unbounded report grows for the life of the room, while exporting whole application objects risks including conversation or credential data.',
    change:
      'Retention is bounded and export fields are explicitly selected. Exports omit transcripts, audio, embeddings and credentials; filters are applied before summary and download.',
    verification:
      'Automated checks cover room authorization, retained-row limits, filtering and sanitized JSON/CSV output.',
    evidence: ['automated'],
    references: [
      'web/src/services/performance.ts',
      'web/src/types/performance.ts',
      'server/artha_mesh/store.py',
      'docs/GO_LIVE.md',
    ],
    outstanding:
      'Utterance identifiers can still be correlated with other records; share reports intentionally and download before room expiry.',
  },
  {
    id: 'report-tab-experience',
    date: '2026-10-31',
    status: 'improved',
    area: 'experience',
    title: 'Reference-inspired blue waveform branding',
    summary:
      'The owner-selected striped waveform is recreated as a transparent vector for the sidebar and call header, with royal-blue/cyan on light surfaces and lighter blue/cyan on charcoal. A compact waveform identifies the browser tab. The larger conversation illustration remains on Home and desktop Prejoin.',
    cause:
      'The owner requested the supplied blue waveform instead of the earlier connected-bar mark. The screenshot background and fine stripes needed a clean vector treatment with surface-aware colour and a separate compact favicon.',
    change:
      'Created a 32-bar vector waveform and a nine-bar compact favicon. The shared Logo renders the full waveform as a CSS mask with surface-specific blue gradients; wider dimensions preserve its horizontal shape at header sizes. No speech or capture behavior changed.',
    verification:
      'Browser checks cover the desktop sidebar and narrow-screen header with no microphone or camera enabled. Both gradient endpoints exceed 3:1 graphical contrast against their intended light/dark surfaces. The favicon switches colour for the browser theme. These are targeted visual checks, not a complete accessibility certification. No provider/API credits were used.',
    evidence: ['automated', 'browser'],
    references: [
      'web/public/artha-waveform.svg',
      'web/public/artha-waveform-icon.svg',
      'web/public/voice-mesh-mark.svg',
      'web/src/components/ConversationIllustration.tsx',
      'web/public/artha-mesh-logo.png',
      'web/public/artha-mesh-mark-transparent.png',
      'web/public/artha-mesh-logo-blue.png',
      'web/src/components/ui.tsx',
      'web/src/pages/Meeting.tsx',
      'web/src/pages/Performance.tsx',
      'web/src/theme.css',
      'web/src/pages/Prejoin.tsx',
      'web/src/components/ConferenceStatus.tsx',
      'web/src/hooks/useTransportMetrics.ts',
      'web/src/services/transportMetrics.test.ts',
    ],
    outstanding:
      'Actual device listening, camera and recovery acceptance remain separate checks. Broader accessibility checks, latency optimization, detector accuracy validation and voice cloning remain pending.',
  },
  {
    id: 'credit-guardrails',
    date: '2026-10-24',
    status: 'improved',
    area: 'usage',
    title: 'Paid flows require permission and retain their usage record',
    summary:
      'Short-lived operator grants and atomic daily caps protect each paid flow; reserved units, rupees and programme credits stay separate.',
    cause:
      'Limited provider allowances need explicit application budgets in addition to each vendor’s own account limits.',
    change:
      'The ledger checks explicit flow budgets and expiry before upstream work, binds ongoing streams to the same grant, and records safe measurements. The Usage page distinguishes manual balance snapshots, reference prices and unverified actual charges; financial evidence is hidden on public responses by default.',
    verification:
      'Mocked checks cover grant expiry/replacement, atomic caps, privacy, reconciliation and a bounded test runner. One separately approved Gnani TTS→STT check passed and closed its grant; the Usage page records its units and timings. Actual invoice and cloning checks remain pending.',
    evidence: ['automated', 'review', 'live-provider'],
    references: [
      'server/artha_mesh/services/usage.py',
      'server/artha_mesh/services/approvals.py',
      'server/tests/test_approvals.py',
      'scripts/check_gnani.py',
      'docs/GNANI_CHECKS.md',
      'server/tests/test_usage.py',
      'server/tests/test_credit_transport.py',
      'docs/CREDIT_CONTROLS.md',
    ],
    outstanding:
      'Obtain human permission before each actual test. Reconcile charges against the provider dashboard and confirm enrollment/cloned-synthesis pricing. Reference costs are not a guaranteed invoice or a provider-enforced rupee cap.',
  },
  {
    id: 'provider-admission-lifecycle',
    date: '2026-10-24',
    status: 'fixed',
    area: 'usage',
    title: 'Queued provider work rechecks its listener before spending',
    summary:
      'A language branch cannot use a newly available provider slot after its speaker expires or its last listener leaves.',
    cause:
      'A delivery check made before a bounded concurrency wait could become stale while the branch waited for admission.',
    change:
      'Each branch carries a scoped eligibility check. The guard runs it after acquiring a provider slot and before reserving units or calling the upstream service; cancellation releases the slot.',
    verification:
      'Four mocked MT/TTS admission fixtures expire the source or remove the last listener while work waits. They verify no upstream request and no usage increment for the abandoned branch.',
    evidence: ['automated', 'review'],
    references: [
      'server/artha_mesh/services/pipeline.py',
      'server/artha_mesh/services/usage.py',
      'server/tests/test_usage.py',
    ],
    outstanding:
      'Exercise the same lifecycle transitions during a live multi-party acceptance call.',
  },
  {
    id: 'real-provider-acceptance',
    date: '2026-10-28',
    status: 'pending',
    area: 'delivery',
    title: 'Hindi–Tamil standard-voice test prepared; live test pending',
    summary:
      'Local original audio is reported complete. The next test is two typed Hindi–Tamil turns with standard voices; microphone interpretation and cloning have separate later approvals.',
    cause:
      'Mock protocol checks and synthetic audio establish integration behavior, not language accuracy or voice similarity.',
    change:
      'An offline plan fixes two everyday phrases and zero STT/enrollment budgets. Target-language stock voices are Nalini for Hindi and Trisha for Tamil. The existing key is retained; the hosted Evon request contract still needs its official quickstart.',
    verification:
      'The earlier approved Gnani speech round trip passed on 24 October. Offline checks cover the new plan and stock voices. Read-only dashboard inspection on 27 October found no Evon section; Documentation opens speech references and Agents requires an official email. The hosted Evon contract remains pending. No new inference call or approval grant was made.',
    evidence: ['automated', 'live-provider', 'live-pending'],
    references: [
      'docs/HINDI_TAMIL_TEST.md',
      'scripts/plan_translation_test.py',
      'server/tests/test_translation_plan.py',
      'server/tests/test_provider_contracts.py',
      'docs/VALIDATION.md',
    ],
    outstanding:
      'Obtain the Evon endpoint/model/authentication guide, review the exact two-turn usage limits and obtain explicit approval. Then check meaning and target speech in both directions before preparing the separate microphone flow. Cloning stays deferred.',
  },
  {
    id: 'listener-latency',
    date: '2026-10-30',
    status: 'pending',
    area: 'measurement',
    title: 'Synthetic speech-end routing is measured; physical playback remains pending',
    summary: 'Eleven local RTC observations completed without provider calls. Ten warm trials recorded decoded-audio p50 926.287 ms and p95 956.797 ms. The under-two-second physical playback goal remains unverified.',
    cause:
      'Provider-start timings and browser test tones did not measure source speech end to listener output. Two initial fixture preflights lacked inert configuration, and a later run hit native capture cancellation after two trials. Those failed runs remain separate from the final result.',
    change:
      'Added a same-process speech-end fixture with cooperative stopping to avoid concurrent native capture shutdown. The interface separates decoded RTC, estimated rendering and physical playback. A manual shared-recording WAV/annotation workflow and ten-language physical gates prepare the next tests without authorizing providers or opening devices.',
    verification:
      'The final two-peer local SFU fixture passed 11/11 with no cleanup failures or provider calls: first route 1,042.113 ms; ten warm observations p50 926.287 ms/p95 956.797 ms; all eleven p50 927.99 ms/p95 1,042.113 ms. Its test doubles intentionally include 600 ms silence, 100 ms MT and 50 ms TTS. These numbers establish neither Gnani/Evon timing nor acoustic output. The original preflight/native cancellation failures are retained; production first-chunk dispatch has separate evidence.',
    evidence: ['automated', 'synthetic-rtc', 'review', 'live-pending'],
    references: ['docs/SPEECH_END_LATENCY.md', 'scripts/measure_local_speech_end.py', 'scripts/measure_speech_end_playback.py', 'scripts/plan_latency_language_workflow.py', 'web/src/data/speechEndLatencyResults.json', 'web/src/components/SpeechEndLatencyEvidence.tsx', 'web/src/components/LatencyLanguageGate.tsx'],
    outstanding:
      'Collect reviewed shared-clock acoustic/electrical captures using live standard voices. Each direction needs at least ten qualifying warm attempts, all complete, with p50 and p95 strictly below 2,000 ms before expansion review. Preserve first-route timing, failures, overlap and duplicate captures. Human meaning, physical devices and the 90-pair matrix remain unverified; paid tests still need approval and cloning stays deferred.',
  },
  {
    id: 'deployment-acceptance',
    date: '2026-10-24',
    status: 'pending',
    area: 'delivery',
    title: 'Full-stack hosting and India residency require deployment evidence',
    summary:
      'The self-hosted VM configuration generator and setup page are implemented; actual server and provider acceptance remain pending.',
    cause:
      'Local builds and configuration files do not establish reachable production media, GPU capacity or processing locations.',
    change:
      'An offline generator prepares own-key LiveKit, shared-port HTTPS/TURN routing, one API worker and persistent usage counters. A separate setup page reports redacted configuration checks. System fonts remove the external font request.',
    verification:
      'Backend readiness and frontend validation tests passed. Browser checks covered mobile/desktop layouts, safe refresh and unknown status with the service offline. No production container, certificate or real-provider acceptance has been performed.',
    evidence: ['automated', 'browser', 'live-pending'],
    references: [
      'scripts/prepare_deployment.py',
      'deploy/production/README.md',
      'server/artha_mesh/services/readiness.py',
      'web/src/pages/Deployment.tsx',
      'docs/INDIA_HOSTING.md',
      'docs/VALIDATION.md',
      'docs/GO_LIVE.md',
    ],
    outstanding:
      'Supply the server/domain, Gnani access and approved Evon endpoint or GPU compute. Verify certificates, UDP/TURN, model contracts, recovery and actual processing/logging regions before claiming live completion or India-only processing.',
  },
];

export function filterJournal(entries: DeveloperJournalEntry[], filter: JournalFilter) {
  const query = filter.search.trim().toLocaleLowerCase();
  return entries.filter((entry) => {
    if (filter.status !== 'all' && entry.status !== filter.status) return false;
    if (filter.area !== 'all' && entry.area !== filter.area) return false;
    if (!query) return true;
    return [
      entry.id,
      entry.title,
      entry.summary,
      entry.cause,
      entry.change,
      entry.verification,
      entry.outstanding ?? '',
      JOURNAL_AREA_LABELS[entry.area],
      ...entry.references,
    ]
      .join(' ')
      .toLocaleLowerCase()
      .includes(query);
  });
}

export function journalReport(entries: DeveloperJournalEntry[]) {
  return {
    schema_version: 1,
    record_type: 'manually_maintained_development_journal',
    last_updated: JOURNAL_UPDATED,
    scope: 'Track B',
    note: 'Static engineering record. Evidence levels are explicit; this is not a live activity log or production certification.',
    entry_count: entries.length,
    entries: entries.map((entry) => ({
      ...entry,
      references: [...entry.references],
      evidence: [...entry.evidence],
    })),
  };
}
