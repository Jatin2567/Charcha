import storedEvidence from '../data/speechEndLatencyResults.json';

export type SpeechEndCondition = 'first_route' | 'warm_route';
export interface SpeechEndSample {
  trial_id: string;
  condition: SpeechEndCondition;
  source_language: 'hi';
  target_language: 'ta';
  status: 'complete' | 'timeout' | 'error';
  source_end_to_decoded_ms: number | null;
  source_end_to_render_estimate_ms: null;
  source_end_to_physical_playback_ms: null;
}
export interface SpeechEndEvidence {
  schema_version: 1;
  record_type: 'speech_end_latency_evidence';
  recorded_on: string;
  evidence_kind: 'synthetic_local_rtc';
  clock: 'single_process_monotonic';
  boundary: 'source_end_to_first_decoded_rtc';
  source_end_reference: 'last_voiced_source_frame_playout';
  physical_playback_measured: false;
  provider_calls: 0;
  screening_mode: 'off';
  voice_cloning: false;
  target_ms: 2000;
  acceptance: 'not_verified';
  samples: SpeechEndSample[];
  summary: {
    attempted: number;
    completed: number;
    failed: number;
    p50_decoded_ms: number | null;
    p95_decoded_ms: number | null;
  };
  limitations: string[];
  source_report_sha256: string;
}
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const offset = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 3_600_000;
const hash = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

/** Nearest-rank offsets retain negative streaming onset; unknown values never become zero. */
export function summarizeSpeechEnd(samples: SpeechEndSample[]) {
  const values = samples
    .filter((row) => row.status === 'complete' && offset(row.source_end_to_decoded_ms))
    .map((row) => row.source_end_to_decoded_ms!)
    .sort((a, b) => a - b);
  const rank = (fraction: number) =>
    values.length ? values[Math.max(0, Math.ceil(values.length * fraction) - 1)] : null;
  return {
    attempted: samples.length,
    completed: values.length,
    failed: samples.filter((row) => row.status !== 'complete').length,
    p50_decoded_ms: rank(0.5),
    p95_decoded_ms: rank(0.95),
  };
}

/** Saved synthetic evidence only. Physical/render estimates and the physical target stay unverified. */
export function speechEndLatencyReport(value: unknown = storedEvidence): SpeechEndEvidence | null {
  if (
    !record(value) ||
    value.schema_version !== 1 ||
    value.record_type !== 'speech_end_latency_evidence'
  )
    return null;
  if (
    value.evidence_kind !== 'synthetic_local_rtc' ||
    value.clock !== 'single_process_monotonic' ||
    value.boundary !== 'source_end_to_first_decoded_rtc' ||
    value.source_end_reference !== 'last_voiced_source_frame_playout' ||
    value.physical_playback_measured !== false ||
    value.provider_calls !== 0 ||
    value.screening_mode !== 'off' ||
    value.voice_cloning !== false ||
    value.target_ms !== 2000 ||
    value.acceptance !== 'not_verified'
  )
    return null;
  if (
    typeof value.recorded_on !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value.recorded_on) ||
    !hash(value.source_report_sha256) ||
    !Array.isArray(value.samples) ||
    value.samples.length > 1000 ||
    !record(value.summary)
  )
    return null;
  if (
    !Array.isArray(value.limitations) ||
    value.limitations.some(
      (row) =>
        typeof row !== 'string' ||
        row.length > 1200 ||
        /vach_[A-Za-z0-9_-]+|Bearer\s+\S+|https?:\/\/|[A-Z]:\\Users\\/i.test(row),
    )
  )
    return null;
  const samples: SpeechEndSample[] = [];
  const ids = new Set<string>();
  for (const row of value.samples) {
    if (
      !record(row) ||
      typeof row.trial_id !== 'string' ||
      !/^[A-Za-z0-9_-]{1,80}$/.test(row.trial_id) ||
      ids.has(row.trial_id) ||
      !['first_route', 'warm_route'].includes(String(row.condition)) ||
      row.source_language !== 'hi' ||
      row.target_language !== 'ta' ||
      !['complete', 'timeout', 'error'].includes(String(row.status)) ||
      row.source_end_to_render_estimate_ms !== null ||
      row.source_end_to_physical_playback_ms !== null
    )
      return null;
    if (
      row.status === 'complete'
        ? !offset(row.source_end_to_decoded_ms)
        : row.source_end_to_decoded_ms !== null
    )
      return null;
    ids.add(row.trial_id);
    samples.push({
      trial_id: row.trial_id,
      condition: row.condition as SpeechEndCondition,
      source_language: 'hi',
      target_language: 'ta',
      status: row.status as SpeechEndSample['status'],
      source_end_to_decoded_ms: row.source_end_to_decoded_ms as number | null,
      source_end_to_render_estimate_ms: null,
      source_end_to_physical_playback_ms: null,
    });
  }
  const summary = summarizeSpeechEnd(samples);
  if (
    Object.entries(summary).some(
      ([key, result]) => (value.summary as Record<string, unknown>)[key] !== result,
    )
  )
    return null;
  return {
    schema_version: 1,
    record_type: 'speech_end_latency_evidence',
    recorded_on: value.recorded_on,
    evidence_kind: 'synthetic_local_rtc',
    clock: 'single_process_monotonic',
    boundary: 'source_end_to_first_decoded_rtc',
    source_end_reference: 'last_voiced_source_frame_playout',
    physical_playback_measured: false,
    provider_calls: 0,
    screening_mode: 'off',
    voice_cloning: false,
    target_ms: 2000,
    acceptance: 'not_verified',
    samples,
    summary,
    limitations: [...value.limitations] as string[],
    source_report_sha256: value.source_report_sha256,
  };
}
