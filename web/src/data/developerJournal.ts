export type JournalStatus = 'fixed' | 'improved' | 'pending';
export type JournalArea =
  | 'audio'
  | 'reliability'
  | 'security'
  | 'measurement'
  | 'experience'
  | 'usage'
  | 'delivery';
export type JournalEvidence = 'automated' | 'synthetic-rtc' | 'browser' | 'review' | 'live-pending';
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
export const JOURNAL_UPDATED = '2026-10-24';
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
    id: 'mute-state',
    date: JOURNAL_UPDATED,
    status: 'fixed',
    area: 'audio',
    title: 'Mute state now follows the server',
    summary:
      'A failed mute update can no longer leave the microphone sending while the interface appears muted.',
    cause:
      'Browser media changes and the room update can finish at different times; a rejected update leaves their states inconsistent.',
    change:
      'The server participant state is authoritative. A failed update mutes the local audio path, disconnecting if muting fails; stale asynchronous operations cannot restore it.',
    verification:
      'The local recovery and routing checks cover mute handling. Synthetic WebRTC checks exercised mute, unmute and expiry gates.',
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
    date: JOURNAL_UPDATED,
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
    date: JOURNAL_UPDATED,
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
    date: JOURNAL_UPDATED,
    status: 'fixed',
    area: 'audio',
    title: 'Same-language forwarding and typed speech share audio safely',
    summary:
      'Forwarded microphone audio now matches the output sample rate, and typed speech can finish playout.',
    cause:
      'The source uses 16 kHz PCM while output uses 24 kHz. Continuous forwarded silence could also keep the shared output queue from draining after typed synthesis.',
    change:
      'Forwarded PCM is resampled to 24 kHz. Source forwarding pauses while synthesis owns that output track, allowing its playout queue to complete.',
    verification:
      'The Hindi/Hindi/Tamil synthetic RTC experiment checked forwarding, non-silent output, typed speech, mute/unmute and expiry.',
    evidence: ['synthetic-rtc', 'automated'],
    references: ['server/artha_mesh/transport/livekit.py', 'scripts/verify_same_language.py'],
    outstanding:
      'Listen for continuity and intelligibility with actual speakers and provider audio.',
  },
  {
    id: 'snapshot-recovery',
    date: JOURNAL_UPDATED,
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
    date: JOURNAL_UPDATED,
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
    date: JOURNAL_UPDATED,
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
    date: JOURNAL_UPDATED,
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
    date: JOURNAL_UPDATED,
    status: 'fixed',
    area: 'experience',
    title: 'Reports open alongside a call without taking its microphone',
    summary:
      'The report tab preserves the ongoing call and shows its technical network statistics.',
    cause:
      'Navigating away from a meeting tears down its media. A plain in-page hash link also conflicts with the application hash router.',
    change:
      'Meeting reports open in a separate tab with room-scoped access. That tab does not connect audio; its network statistics arrive from the active call. The setup shortcut scrolls without changing the route. A smaller minimum page width also avoids horizontal scrolling in narrow browser panels.',
    verification:
      'The browser journey kept the original call connected, filtered 14 scripted branch rows and downloaded a filtered report. Report-tab isolation and statistics conversion have automated checks.',
    evidence: ['automated', 'browser'],
    references: [
      'web/src/pages/Meeting.tsx',
      'web/src/pages/Performance.tsx',
      'web/src/hooks/useTransportMetrics.ts',
      'web/src/services/transportMetrics.test.ts',
    ],
    outstanding:
      'Actual device statistics and real-call recovery remain live checks. Scripted rows stay excluded from live percentiles.',
  },
  {
    id: 'credit-guardrails',
    date: JOURNAL_UPDATED,
    status: 'improved',
    area: 'usage',
    title: 'Daily usage caps survive server restarts',
    summary:
      'Atomic daily reservations limit provider attempts and connected recognition time; usage remains separate from the provider balance.',
    cause:
      'Limited provider allowances need explicit application budgets in addition to each vendor’s own account limits.',
    change:
      'A persistent metadata-only ledger enforces configurable UTC daily caps, zero-limit blocking and bounded concurrency. Muted, empty and same-language-only rooms skip recognition; authentication/quota failures stop retries. Same-language forwarding continues with generated captions paused.',
    verification:
      'Mocked tests check atomic reservations, restart persistence, date rollover, failures, unavailable storage, idle-stream termination and terminal provider errors. No actual provider inference or billing validation was performed.',
    evidence: ['automated', 'review'],
    references: [
      'server/artha_mesh/services/usage.py',
      'server/tests/test_usage.py',
      'server/tests/test_credit_transport.py',
      'docs/CREDIT_CONTROLS.md',
    ],
    outstanding:
      'Set allowances from the actual provider account. App estimates are not an invoice or a vendor-enforced spending guarantee.',
  },
  {
    id: 'provider-admission-lifecycle',
    date: JOURNAL_UPDATED,
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
    date: JOURNAL_UPDATED,
    status: 'pending',
    area: 'delivery',
    title: 'Real-provider speech and clone acceptance',
    summary:
      'Working Gnani/LiveKit access, an Evon endpoint and consenting speakers are still required.',
    cause:
      'Mock protocol checks and synthetic audio establish integration behavior, not language accuracy or voice similarity.',
    change:
      'A staged acceptance checklist starts with short standard-voice Hindi→Tamil phrases, reverses direction, adds Bengali, and then checks consented cloning and deletion.',
    verification:
      'Pending real-provider calls and human review. Draft evaluation cases are available but are not certified ground truth.',
    evidence: ['live-pending'],
    references: ['docs/GO_LIVE.md', 'docs/EVALUATION.md', 'docs/VALIDATION.md'],
    outstanding:
      'Check account entitlements, actual model/voice IDs, quotas, meaning, names, numbers, negation and cross-language clone quality.',
  },
  {
    id: 'listener-latency',
    date: JOURNAL_UPDATED,
    status: 'pending',
    area: 'measurement',
    title: 'Audible listener latency needs a shared-timebase test',
    summary: 'No real ear-to-ear latency result or under-800-ms achievement is claimed.',
    cause:
      'Server first-PCM dispatch excludes parts of capture, VAD buffering, transport and receiver playout.',
    change:
      'The measurement guide defines a consented two-channel or synchronized capture: source phrase end to first audible translated sample at the receiver.',
    verification:
      'The procedure is documented. Actual recordings, annotations, sample counts and p50/p95 remain pending.',
    evidence: ['live-pending'],
    references: ['docs/GO_LIVE.md', 'docs/VALIDATION.md'],
    outstanding:
      'Evaluate directions, phrase lengths, standard/cloned voices, concurrent speakers and the intended networks; report failures alongside timing.',
  },
  {
    id: 'deployment-acceptance',
    date: JOURNAL_UPDATED,
    status: 'pending',
    area: 'delivery',
    title: 'Full-stack hosting and India residency require deployment evidence',
    summary:
      'The static private preview is available; the Python speech service and Evon need their own running infrastructure.',
    cause:
      'Local builds and configuration files do not establish reachable production media, GPU capacity or processing locations.',
    change:
      'Deployment configuration and host checks are documented. The current in-memory room architecture requires a single API worker.',
    verification:
      'Production frontend build passed. Docker acceptance was not run because the local daemon was unavailable; the optional GPU model was not downloaded or started.',
    evidence: ['automated', 'live-pending'],
    references: [
      'compose.yaml',
      'Dockerfile.api',
      'Dockerfile.web',
      'docs/VALIDATION.md',
      'docs/GO_LIVE.md',
    ],
    outstanding:
      'Verify HTTPS/WSS, media reachability, GPU/model startup, recovery, and every actual worker, media, inference, provider and logging region before claiming India-only processing.',
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
