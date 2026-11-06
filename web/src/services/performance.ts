import { API_BASE } from './api';
import type { Language } from '../types/domain';
import type {
  PerformanceFilter,
  PerformanceReport,
  PerformanceSample,
  PerformanceSummary,
  ReadinessReport,
  MeetingReportEntry,
  PersistenceStatus,
} from '../types/performance';

export const DEFAULT_FILTER: PerformanceFilter = {
  direction: 'all',
  input: 'all',
  voice: 'all',
  status: 'all',
};
export const directionKey = (
  sample: Pick<PerformanceSample, 'source_language' | 'target_language'>,
) => `${sample.source_language}:${sample.target_language}`;
const finite = (value: number | null): value is number =>
  value !== null && Number.isFinite(value) && value >= 0;
export const measuredSamples = (samples: PerformanceSample[]) =>
  samples.filter(
    (sample) =>
      sample.measurement === 'server_first_pcm' &&
      sample.status === 'complete' &&
      finite(sample.total_ms),
  );

/** Nearest-rank percentiles match the server report. Never turn an empty set into 0 ms. */
export function percentile(values: (number | null)[], fraction: number): number | null {
  const ordered = values.filter(finite).sort((a, b) => a - b);
  if (!ordered.length) return null;
  return ordered[Math.max(0, Math.ceil(Math.min(1, Math.max(0, fraction)) * ordered.length) - 1)];
}
export function filterSamples(samples: PerformanceSample[], filter: PerformanceFilter) {
  return samples.filter(
    (sample) =>
      (filter.direction === 'all' || directionKey(sample) === filter.direction) &&
      (filter.input === 'all' || sample.input_kind === filter.input) &&
      (filter.voice === 'all' || sample.voice_mode === filter.voice) &&
      (filter.status === 'all' || sample.status === filter.status),
  );
}
export function summarize(samples: PerformanceSample[]): PerformanceSummary {
  const measured = measuredSamples(samples);
  const groups = [...new Set(samples.map(directionKey))].sort();
  const counts = (entries: PerformanceSample[]) => ({
    sample_count: entries.length,
    success_count: entries.filter((s) => s.status === 'complete').length,
    error_count: entries.filter((s) => s.status === 'error').length,
    cancelled_count: entries.filter((s) => s.status === 'cancelled').length,
    live_sample_count: measuredSamples(entries).length,
    p50_ms: percentile(
      measuredSamples(entries).map((s) => s.total_ms),
      0.5,
    ),
    p95_ms: percentile(
      measuredSamples(entries).map((s) => s.total_ms),
      0.95,
    ),
  });
  return {
    ...counts(samples),
    live_sample_count: measured.length,
    forwarded_count: samples.filter((s) => s.measurement === 'source_forwarded').length,
    simulated_count: samples.filter((s) => s.measurement === 'simulated').length,
    by_direction: groups.map((direction) => {
      const entries = samples.filter((s) => directionKey(s) === direction);
      const [source_language, target_language] = direction.split(':') as [Language, Language];
      return { source_language, target_language, ...counts(entries) };
    }),
  };
}
export function emptyPerformance(roomCode: string, mode: PerformanceReport['mode']): PerformanceReport {
  return {
    room_code: roomCode,
    mode,
    generated_at: new Date().toISOString(),
    measurement: {
      boundary: 'server_first_pcm',
      stt: 'processing_to_transcript',
      total: 'queue_to_first_pcm_plus_stt',
      receiver_playback_measured: false,
      retention_limit: 1000,
    },
    summary: summarize([]),
    samples: [],
  };
}
export function referenceReadiness(): ReadinessReport {
  return {
    mode: 'demo',
    generated_at: new Date().toISOString(),
    provider_verification: 'not_checked',
    requirements: [
      [
        'GNANI_API_KEY',
        'Gnani access',
        'Gnani',
        true,
        'Access to Prisma speech recognition, Timbre speech synthesis and voice-clone embeddings. Confirm your account has access to all three.',
      ],
      [
        'LIVEKIT_URL',
        'LiveKit room URL',
        'LiveKit',
        true,
        'A browser-reachable secure WebSocket URL. Choose India region hosting or a self-hosted deployment according to your residency requirements.',
      ],
      [
        'LIVEKIT_API_KEY',
        'LiveKit API key',
        'LiveKit',
        true,
        'Server-side room and participant token signing.',
      ],
      [
        'LIVEKIT_API_SECRET',
        'LiveKit API secret',
        'LiveKit',
        true,
        'Keep this secret only in the server environment.',
      ],
      [
        'EVON_BASE_URL',
        'Evon inference endpoint',
        'Translation',
        true,
        'A running OpenAI-compatible /v1 inference endpoint. Hosting the open model requires suitable compute.',
      ],
      [
        'EVON_MODEL',
        'Evon served model name',
        'Translation',
        true,
        'The exact model identifier served by your Evon endpoint.',
      ],
      [
        'EVON_API_KEY',
        'Evon endpoint access key',
        'Translation',
        false,
        'Required only if your inference endpoint enables authentication.',
      ],
      [
        'TIMBRE_MODEL',
        'Timbre model',
        'Voice defaults',
        false,
        'Optional override. The server includes a default; confirm model availability with your Gnani account.',
      ],
      [
        'TIMBRE_VOICE',
        'Standard voice',
        'Voice defaults',
        false,
        'Optional override for the standard speaker voice. Cloning uses a separate, consented voice reference.',
      ],
    ].map(([key, label, group, required, detail]) => ({
      key: key as string,
      label: label as string,
      group: group as string,
      required: required as boolean,
      detail: detail as string,
      configured: false,
    })),
    deployment_checks: [
      {
        key: 'https',
        label: 'Secure application URL',
        status: 'manual',
        detail:
          'Deploy frontend and API with HTTPS, correct CORS origins and WebSocket forwarding. Microphones require a secure context outside localhost.',
      },
      {
        key: 'network',
        label: 'LiveKit connectivity',
        status: 'manual',
        detail:
          'Verify WebRTC and TURN connectivity from two separate devices or networks. Test speaker output and microphone permissions.',
      },
      {
        key: 'region',
        label: 'Data location',
        status: 'manual',
        detail:
          'Confirm LiveKit, API, Evon compute, Gnani processing and logs meet your intended India hosting requirements. A configured URL does not verify residency.',
      },
      {
        key: 'speakers',
        label: 'Consenting test speakers',
        status: 'manual',
        detail:
          'Arrange Hindi, Tamil and Bengali speakers, headphones and a quiet space. Record voice references only after explicit consent.',
      },
      {
        key: 'evaluation',
        label: 'Bilingual accuracy review',
        status: 'manual',
        detail:
          'Review names, numbers, negation, meaning and cloned-voice quality using the evaluation fixtures and an agreed acceptance target.',
      },
      {
        key: 'recovery',
        label: 'Recovery & submission',
        status: 'manual',
        detail:
          'Exercise mute, language changes, disconnect/rejoin, provider failure and voice deletion. Capture your 60-second demonstration after live checks pass.',
      },
    ],
  };
}

async function fetchReport<T>(
  path: string,
  token: string | undefined,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: 'no-store',
  });
  if (!response.ok)
    throw new Error(
      response.status === 401 || response.status === 403
        ? 'Room access has expired. Keep this report for reference and join a room again to collect new measurements.'
        : `Measurements are unavailable (${response.status}). Check the workspace service and try again.`,
    );
  return response.json() as Promise<T>;
}
export const fetchPerformance = (roomCode: string, token: string, signal: AbortSignal) =>
  fetchReport<PerformanceReport>(
    `/rooms/${encodeURIComponent(roomCode)}/performance`,
    token,
    signal,
  );
export const fetchReadiness = (signal: AbortSignal) =>
  fetchReport<ReadinessReport>('/readiness', undefined, signal);

export const fetchCurrentCallPerformance = (signal: AbortSignal) =>
  fetchReport<PerformanceReport | null>('/account/call-performance', undefined, signal);

export const fetchPerformanceHistory = (signal: AbortSignal) =>
  fetchReport<{ reports: MeetingReportEntry[]; retention_days: number; persistence?: PersistenceStatus }>(
    '/account/performance-history', undefined, signal);
export const fetchSavedPerformance = (reportId: string, signal: AbortSignal) =>
  fetchReport<PerformanceReport>(`/account/performance-history/${encodeURIComponent(reportId)}`, undefined, signal);

/** Explicit allowlist: never spread raw API data into an exported report. */
export function sanitizedReport(report: PerformanceReport, filter: PerformanceFilter) {
  const samples = filterSamples(report.samples, filter).map((s) => ({
    id: s.id,
    utterance_id: s.utterance_id,
    source_language: s.source_language,
    target_language: s.target_language,
    input_kind: s.input_kind,
    voice_mode: s.voice_mode,
    status: s.status,
    measurement: s.measurement,
    queue_ms: s.queue_ms,
    queue_depth: s.queue_depth ?? null,
    preparation_ms: s.preparation_ms ?? null,
    output_wait_ms: s.output_wait_ms ?? null,
    stt_ms: s.stt_ms,
    source_end_status: s.source_end_status ?? 'not_recorded',
    source_end_to_transcript_ms: s.source_end_to_transcript_ms ?? null,
    source_end_to_first_pcm_ms: s.source_end_to_first_pcm_ms ?? null,
    mt_ms: s.mt_ms,
    tts_first_pcm_ms: s.tts_first_pcm_ms,
    total_ms: s.total_ms,
    created_at: s.created_at,
    error_stage: s.error_stage ?? null,
  }));
  return {
    schema_version: 1,
    mode: report.mode,
    generated_at: report.generated_at,
    filters: {
      direction: filter.direction,
      input: filter.input,
      voice: filter.voice,
      status: filter.status,
    },
    measurement: {
      boundary: 'server_first_pcm',
      stt: 'processing_to_transcript',
      total: 'queue_to_first_pcm_plus_stt',
      receiver_playback_measured: false,
      total_coverage: 'partial_when_stt_missing',
      retention_limit: report.measurement.retention_limit,
    },
    summary: summarize(samples),
    samples,
  };
}
/** Quote CSV delimiters and neutralize spreadsheet formulas, even inside quoted cells. */
export function csvCell(value: unknown): string {
  let text = value == null ? '' : String(value);
  if (/^[\s\u0000-\u001f]*[=+@-]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}
export function performanceCsv(report: PerformanceReport, filter: PerformanceFilter): string {
  const rows = sanitizedReport(report, filter).samples;
  const fields: (keyof PerformanceSample)[] = [
    'id',
    'utterance_id',
    'created_at',
    'source_language',
    'target_language',
    'input_kind',
    'voice_mode',
    'status',
    'measurement',
    'queue_ms',
    'queue_depth',
    'preparation_ms',
    'output_wait_ms',
    'stt_ms',
    'source_end_status',
    'source_end_to_transcript_ms',
    'source_end_to_first_pcm_ms',
    'mt_ms',
    'tts_first_pcm_ms',
    'total_ms',
    'error_stage',
  ];
  return [
    fields.map(csvCell).join(','),
    ...rows.map((row) => fields.map((key) => csvCell(row[key])).join(',')),
  ].join('\r\n');
}
