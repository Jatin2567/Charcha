export const PUBLIC_SPEECH_LANGUAGES = ['hi', 'ta', 'bn', 'te', 'mr'] as const;
export type PublicSpeechLanguage = (typeof PUBLIC_SPEECH_LANGUAGES)[number];
const PREFIXES = [500, 1000, 2000, 3000] as const;
const REVISION = '70bb2e84b976b7e960aa89f1c648e09c59f894dd';
const DATASET_URL = 'https://huggingface.co/datasets/google/fleurs';
const MODEL_ID = 'SpeechAntiSpoofingBenchmarks/AASIST';

export interface PublicSpeechLanguageResult {
  language: PublicSpeechLanguage;
  recordings: number;
  allow: number;
  suspicious: number;
  unknown: number;
  errors: number;
  unattempted: number;
  compute_p50_ms: number | null;
  compute_p95_ms: number | null;
}
export interface PublicSpeechPrefixResult {
  observed_audio_ms: (typeof PREFIXES)[number];
  recordings: number;
  suspicious: number;
  unknown: number;
  errors: number;
  unattempted: number;
  verdict_changes_from_full: number | null;
  paired_comparisons: number;
}
export interface PublicHumanScreeningReport {
  schema_version: 1;
  record_type: 'saved_public_human_screening_pilot';
  status: 'not_run' | 'complete' | 'partial';
  measured_at: string | null;
  source: {
    dataset: 'google/fleurs';
    revision: string;
    license: 'cc-by-4.0';
    split: 'test';
    url: string;
  };
  model: { id: string; sha256: string | null };
  baseline_ms: 4037.5;
  baseline_by_language: PublicSpeechLanguageResult[];
  prefix_summary: PublicSpeechPrefixResult[];
  provider_calls: 0;
  voice_cloning: false;
  independent_speaker_count: null;
  synthetic_recordings: 0;
  ai_detection_rate: null;
  accuracy: null;
  live_window_changed: false;
}

const object = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
const count = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 50;
const timing = (value: unknown): value is number | null =>
  value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0);

/** Validate and copy an explicit public contract; never export the runtime input. */
export function publicHumanScreeningReport(value: unknown): PublicHumanScreeningReport | null {
  const input = object(value);
  if (!input) return null;
  const source = object(input.source),
    model = object(input.model);
  if (
    input.schema_version !== 1 ||
    input.record_type !== 'saved_public_human_screening_pilot' ||
    !['not_run', 'complete', 'partial'].includes(String(input.status)) ||
    input.provider_calls !== 0 ||
    input.voice_cloning !== false ||
    input.live_window_changed !== false ||
    input.independent_speaker_count !== null ||
    input.synthetic_recordings !== 0 ||
    input.ai_detection_rate !== null ||
    input.accuracy !== null ||
    input.baseline_ms !== 4037.5 ||
    source?.dataset !== 'google/fleurs' ||
    source.revision !== REVISION ||
    source.license !== 'cc-by-4.0' ||
    source.split !== 'test' ||
    source.url !== DATASET_URL ||
    model?.id !== MODEL_ID ||
    !(
      model.sha256 === null ||
      (typeof model.sha256 === 'string' && /^[a-f\d]{64}$/.test(model.sha256))
    ) ||
    !Array.isArray(input.baseline_by_language) ||
    !Array.isArray(input.prefix_summary)
  )
    return null;

  const baseline: PublicSpeechLanguageResult[] = [];
  for (const candidate of input.baseline_by_language) {
    const row = object(candidate);
    if (!row || !PUBLIC_SPEECH_LANGUAGES.includes(row.language as PublicSpeechLanguage))
      return null;
    if (
      !['recordings', 'allow', 'suspicious', 'unknown', 'errors', 'unattempted'].every((key) =>
        count(row[key]),
      )
    )
      return null;
    const recordings = row.recordings as number;
    const [allow, suspicious, unknown, errors, unattempted] = [
      'allow',
      'suspicious',
      'unknown',
      'errors',
      'unattempted',
    ].map((key) => row[key] as number);
    if (
      allow + suspicious + unknown + errors + unattempted !== recordings ||
      !timing(row.compute_p50_ms) ||
      !timing(row.compute_p95_ms) ||
      (row.compute_p50_ms === null) !== (row.compute_p95_ms === null) ||
      (typeof row.compute_p50_ms === 'number' &&
        typeof row.compute_p95_ms === 'number' &&
        row.compute_p50_ms > row.compute_p95_ms) ||
      (recordings === errors + unattempted && row.compute_p50_ms !== null)
    )
      return null;
    baseline.push({
      language: row.language as PublicSpeechLanguage,
      recordings,
      allow,
      suspicious,
      unknown,
      errors,
      unattempted,
      compute_p50_ms: row.compute_p50_ms,
      compute_p95_ms: row.compute_p95_ms,
    });
  }
  const total = baseline.reduce((sum, row) => sum + row.recordings, 0);
  const baselineCompleted = baseline.reduce(
    (sum, row) => sum + row.recordings - row.errors - row.unattempted,
    0,
  );
  if (total > 50 || new Set(baseline.map((row) => row.language)).size !== baseline.length)
    return null;

  const prefixes: PublicSpeechPrefixResult[] = [];
  for (const candidate of input.prefix_summary) {
    const row = object(candidate);
    if (
      !row ||
      !PREFIXES.includes(row.observed_audio_ms as (typeof PREFIXES)[number]) ||
      !['recordings', 'suspicious', 'unknown', 'errors', 'unattempted', 'paired_comparisons'].every(
        (key) => count(row[key]),
      )
    )
      return null;
    const recordings = row.recordings as number,
      paired = row.paired_comparisons as number;
    if (
      recordings !== total ||
      (row.suspicious as number) +
        (row.unknown as number) +
        (row.errors as number) +
        (row.unattempted as number) >
        recordings ||
      paired > recordings ||
      paired > recordings - (row.errors as number) - (row.unattempted as number) ||
      paired > baselineCompleted ||
      (paired === 0
        ? row.verdict_changes_from_full !== null
        : !count(row.verdict_changes_from_full) || row.verdict_changes_from_full > paired)
    )
      return null;
    prefixes.push({
      observed_audio_ms: row.observed_audio_ms as PublicSpeechPrefixResult['observed_audio_ms'],
      recordings,
      suspicious: row.suspicious as number,
      unknown: row.unknown as number,
      errors: row.errors as number,
      unattempted: row.unattempted as number,
      paired_comparisons: paired,
      verdict_changes_from_full: row.verdict_changes_from_full as number | null,
    });
  }
  if (new Set(prefixes.map((row) => row.observed_audio_ms)).size !== prefixes.length) return null;
  if (input.status === 'not_run') {
    if (input.measured_at !== null || baseline.length || prefixes.length || model.sha256 !== null)
      return null;
  } else {
    if (
      typeof input.measured_at !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2}))?$/.test(input.measured_at) ||
      !Number.isFinite(Date.parse(input.measured_at)) ||
      baseline.length !== 5 ||
      total === 0 ||
      prefixes.length !== 4 ||
      model.sha256 === null
    )
      return null;
    if (
      input.status === 'complete' &&
      (baseline.some((row) => row.recordings === 0 || row.errors || row.unattempted) ||
        prefixes.some(
          (row) => row.errors || row.unattempted || row.paired_comparisons !== row.recordings,
        ))
    )
      return null;
  }
  return {
    schema_version: 1,
    record_type: 'saved_public_human_screening_pilot',
    status: input.status as PublicHumanScreeningReport['status'],
    measured_at: input.measured_at as string | null,
    source: {
      dataset: 'google/fleurs',
      revision: REVISION,
      license: 'cc-by-4.0',
      split: 'test',
      url: DATASET_URL,
    },
    model: { id: MODEL_ID, sha256: model.sha256 as string | null },
    baseline_ms: 4037.5,
    baseline_by_language: baseline,
    prefix_summary: prefixes,
    provider_calls: 0,
    voice_cloning: false,
    independent_speaker_count: null,
    synthetic_recordings: 0,
    ai_detection_rate: null,
    accuracy: null,
    live_window_changed: false,
  };
}
