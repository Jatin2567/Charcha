import storedEvidence from '../data/hindiTamilProviderResults.json';

export const PROVIDER_CHAIN_COMPLETE = 'provider_chain_complete_meaning_review_pending';
type CaseStatus = typeof PROVIDER_CHAIN_COMPLETE | 'unattempted' | 'error' | 'cancelled';
type Units = {
  stt_seconds: number;
  stt_connections: number;
  mt_requests: number;
  mt_characters: number;
  tts_requests: number;
  tts_characters: number;
  voice_enrollments: number;
};
type Synthesis = { first_pcm_ms: number; complete_ms: number };
export interface ControlledProviderCase {
  case_id: string;
  source_language: 'hi' | 'ta';
  target_language: 'hi' | 'ta';
  status: CaseStatus;
  meaning_review: 'pending';
  source_preparation: Synthesis | null;
  stt_final_ms: number | null;
  mt_complete_ms: number | null;
  target_synthesis: Synthesis | null;
  stt_start_to_target_first_pcm_ms: number | null;
  stt_start_to_target_complete_ms: number | null;
}
export interface ControlledProviderEvidence {
  schema_version: 1;
  record_type: 'controlled_hindi_tamil_provider_evidence';
  recorded_on: string;
  source_report_sha256: string;
  plan_sha256: string;
  source_provenance: 'deliberately_generated_stock_voice_utterances';
  voice_mode: 'standard';
  status: typeof PROVIDER_CHAIN_COMPLETE | 'stopped_no_retry' | 'cancelled';
  error_stage: string | null;
  cases: ControlledProviderCase[];
  used: Units | null;
  caps: Units;
  wall_seconds: number;
  wall_target_seconds: 240;
  wall_target_exceeded: boolean;
  cleanup_complete: boolean;
  meaning_review: 'pending';
  rtc_tested: false;
  physical_microphone_tested: false;
  listener_latency_ms: null;
  voice_cloning: false;
  screening_mode: 'off';
  automatic_retries: 0;
  cost_reference: {
    currency: 'INR';
    stt_per_hour: 27;
    tts_per_10000_characters: 27;
    local_usage_reference_inr: number | null;
    approved_maximum_reference_inr: 2.385;
    actual_provider_charge_inr: null;
    actual_modal_charge_usd: null;
    programme_credits_used: null;
  };
  boundary: string;
  usage_boundary: string;
}
const CAPS: Units = {
  stt_seconds: 30,
  stt_connections: 2,
  mt_requests: 2,
  mt_characters: 1000,
  tts_requests: 4,
  tts_characters: 800,
  voice_enrollments: 0,
};
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0;
const milliseconds = (value: unknown) => value === null || finite(value);
const hash = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const synthesis = (value: unknown): value is Synthesis | null =>
  value === null ||
  (record(value) &&
    finite(value.first_pcm_ms) &&
    finite(value.complete_ms) &&
    value.first_pcm_ms <= value.complete_ms);

/** Curated controlled-chain evidence only; never accepts room samples or raw runner reports. */
export function hindiTamilProviderReport(
  value: unknown = storedEvidence,
): ControlledProviderEvidence | null {
  if (
    !record(value) ||
    value.schema_version !== 1 ||
    value.record_type !== 'controlled_hindi_tamil_provider_evidence'
  )
    return null;
  if (
    value.source_provenance !== 'deliberately_generated_stock_voice_utterances' ||
    value.voice_mode !== 'standard' ||
    value.rtc_tested !== false ||
    value.physical_microphone_tested !== false ||
    value.voice_cloning !== false ||
    value.screening_mode !== 'off' ||
    value.automatic_retries !== 0 ||
    value.listener_latency_ms !== null ||
    value.meaning_review !== 'pending'
  )
    return null;
  if (
    typeof value.recorded_on !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value.recorded_on) ||
    !hash(value.source_report_sha256) ||
    !hash(value.plan_sha256)
  )
    return null;
  if (
    ![PROVIDER_CHAIN_COMPLETE, 'stopped_no_retry', 'cancelled'].includes(String(value.status)) ||
    ![
      null,
      'approval',
      'configuration',
      'source_tts',
      'stt',
      'mt',
      'target_tts',
      'cancelled',
    ].includes(value.error_stage as null | string)
  )
    return null;
  if (
    !finite(value.wall_seconds) ||
    value.wall_seconds > 3600 ||
    typeof value.cleanup_complete !== 'boolean' ||
    value.wall_target_seconds !== 240 ||
    value.wall_target_exceeded !== value.wall_seconds > 240
  )
    return null;
  if (
    !record(value.caps) ||
    Object.entries(CAPS).some(([key, cap]) => (value.caps as Record<string, unknown>)[key] !== cap)
  )
    return null;
  let used: Units | null = null;
  if (value.used !== null) {
    if (
      !record(value.used) ||
      Object.entries(CAPS).some(
        ([key, cap]) =>
          !Number.isInteger((value.used as Record<string, unknown>)[key]) ||
          ((value.used as Record<string, unknown>)[key] as number) < 0 ||
          ((value.used as Record<string, unknown>)[key] as number) > cap,
      )
    )
      return null;
    used = Object.fromEntries(
      Object.keys(CAPS).map((key) => [key, (value.used as Record<string, number>)[key]]),
    ) as Units;
  }
  const expected = [
    ['hi-ta-meeting-time', 'hi', 'ta'],
    ['ta-hi-book-colour', 'ta', 'hi'],
  ];
  if (!Array.isArray(value.cases) || value.cases.length !== 2) return null;
  const cases: ControlledProviderCase[] = [];
  for (const [index, row] of value.cases.entries()) {
    if (
      !record(row) ||
      row.case_id !== expected[index][0] ||
      row.source_language !== expected[index][1] ||
      row.target_language !== expected[index][2] ||
      ![PROVIDER_CHAIN_COMPLETE, 'unattempted', 'error', 'cancelled'].includes(
        String(row.status),
      ) ||
      row.meaning_review !== 'pending'
    )
      return null;
    if (
      ![
        row.stt_final_ms,
        row.mt_complete_ms,
        row.stt_start_to_target_first_pcm_ms,
        row.stt_start_to_target_complete_ms,
      ].every(milliseconds) ||
      !synthesis(row.source_preparation) ||
      !synthesis(row.target_synthesis)
    )
      return null;
    if (
      row.status === PROVIDER_CHAIN_COMPLETE &&
      (row.source_preparation === null ||
        row.target_synthesis === null ||
        [
          row.stt_final_ms,
          row.mt_complete_ms,
          row.stt_start_to_target_first_pcm_ms,
          row.stt_start_to_target_complete_ms,
        ].some((number) => number === null))
    )
      return null;
    cases.push({
      case_id: expected[index][0],
      source_language: expected[index][1] as 'hi' | 'ta',
      target_language: expected[index][2] as 'hi' | 'ta',
      status: row.status as CaseStatus,
      meaning_review: 'pending',
      source_preparation:
        row.source_preparation === null
          ? null
          : {
              first_pcm_ms: row.source_preparation.first_pcm_ms,
              complete_ms: row.source_preparation.complete_ms,
            },
      stt_final_ms: row.stt_final_ms as number | null,
      mt_complete_ms: row.mt_complete_ms as number | null,
      target_synthesis:
        row.target_synthesis === null
          ? null
          : {
              first_pcm_ms: row.target_synthesis.first_pcm_ms,
              complete_ms: row.target_synthesis.complete_ms,
            },
      stt_start_to_target_first_pcm_ms: row.stt_start_to_target_first_pcm_ms as number | null,
      stt_start_to_target_complete_ms: row.stt_start_to_target_complete_ms as number | null,
    });
  }
  if (
    value.status === PROVIDER_CHAIN_COMPLETE &&
    (!used ||
      !value.cleanup_complete ||
      value.error_stage !== null ||
      cases.some((row) => row.status !== PROVIDER_CHAIN_COMPLETE) ||
      used.tts_requests !== 4 ||
      used.stt_connections !== 2 ||
      used.mt_requests !== 2)
  )
    return null;
  const reference =
    used === null
      ? null
      : Math.round(((used.stt_seconds * 27) / 3600 + (used.tts_characters * 27) / 10000) * 1e6) /
        1e6;
  if (
    !record(value.cost_reference) ||
    value.cost_reference.currency !== 'INR' ||
    value.cost_reference.stt_per_hour !== 27 ||
    value.cost_reference.tts_per_10000_characters !== 27 ||
    value.cost_reference.approved_maximum_reference_inr !== 2.385 ||
    value.cost_reference.local_usage_reference_inr !== reference ||
    value.cost_reference.actual_provider_charge_inr !== null ||
    value.cost_reference.actual_modal_charge_usd !== null ||
    value.cost_reference.programme_credits_used !== null
  )
    return null;
  return {
    schema_version: 1,
    record_type: 'controlled_hindi_tamil_provider_evidence',
    recorded_on: value.recorded_on,
    source_report_sha256: value.source_report_sha256,
    plan_sha256: value.plan_sha256,
    source_provenance: 'deliberately_generated_stock_voice_utterances',
    voice_mode: 'standard',
    status: value.status as ControlledProviderEvidence['status'],
    error_stage: value.error_stage as string | null,
    cases,
    used,
    caps: { ...CAPS },
    wall_seconds: value.wall_seconds,
    wall_target_seconds: 240,
    wall_target_exceeded: value.wall_seconds > 240,
    cleanup_complete: value.cleanup_complete,
    meaning_review: 'pending',
    rtc_tested: false,
    physical_microphone_tested: false,
    listener_latency_ms: null,
    voice_cloning: false,
    screening_mode: 'off',
    automatic_retries: 0,
    cost_reference: {
      currency: 'INR',
      stt_per_hour: 27,
      tts_per_10000_characters: 27,
      local_usage_reference_inr: reference,
      approved_maximum_reference_inr: 2.385,
      actual_provider_charge_inr: null,
      actual_modal_charge_usd: null,
      programme_credits_used: null,
    },
    boundary:
      'Stock-source TTS preparation is separate. STT-start to first target PCM includes connection setup and real-time source-audio transmission; it is not speech-end delay. RTC, physical capture and listener playback are excluded.',
    usage_boundary:
      'Exact local request/character reservations. STT seconds are reserved connection units, not verified provider-billed audio time. Reference pricing excludes Modal compute, rounding and taxes.',
  };
}
