import storedEvidence from '../data/tamilHindiFollowupResults.json';
import { PROVIDER_CHAIN_COMPLETE } from './hindiTamilProviderEvidence';

const CAPS = {
  stt_seconds: 25,
  stt_connections: 1,
  mt_requests: 1,
  mt_characters: 500,
  tts_requests: 1,
  tts_characters: 300,
  voice_enrollments: 0,
};
type Units = typeof CAPS;
const INPUT_HASH = '0c3b3c5a5e78fa824bc633cf21c12fac74f88cde0f708b98f46924dc9b987c39';
const MODEL = 'gnani/gnani-evon-v3.3-30B-A3B';
type ReviewedPrompt = 'evon-explicit-target-v2' | 'evon-conversational-target-v3';
const ERROR_CLASSES = [
  'cancelled',
  'timeout',
  'validation_error',
  'provider_error',
  'io_error',
  'unexpected_error',
  'cleanup_error',
  'flow_close_error',
] as const;
export type FollowupError = (typeof ERROR_CLASSES)[number];
export interface TamilHindiFollowupEvidence {
  schema_version: 1;
  record_type: 'controlled_tamil_hindi_followup_evidence';
  recorded_on: string;
  source_report_sha256: string;
  plan_sha256: string;
  input_sha256: typeof INPUT_HASH;
  source_audio_seconds: 3.2;
  source_provenance: 'existing_standard_voice_clip';
  source_language: 'ta';
  target_language: 'hi';
  translation_model: typeof MODEL;
  prompt_version: ReviewedPrompt;
  voice_mode: 'standard';
  status: typeof PROVIDER_CHAIN_COMPLETE | 'stopped_no_retry' | 'cancelled';
  error_stage: 'approval' | 'configuration' | 'stt' | 'mt' | 'target_tts' | 'cancelled' | null;
  error_class: FollowupError | null;
  stt: { requested_model: 'prisma-v3.0'; provider_model: null };
  timings: {
    stt_final_ms: number | null;
    mt_complete_ms: number | null;
    target_tts_first_pcm_ms: number | null;
    target_tts_complete_ms: number | null;
    stt_start_to_target_first_pcm_ms: number | null;
    stt_start_to_target_complete_ms: number | null;
  };
  used: Units | null;
  caps: Units;
  wall_seconds: number;
  cleanup_complete: boolean;
  flow_closed: boolean;
  meaning_review: 'pending';
  rtc_tested: false;
  physical_microphone_tested: false;
  listener_latency_ms: null;
  voice_cloning: false;
  screening_mode: 'off';
  automatic_retries: 0;
  source_tts_requests: 0;
  cost_reference: {
    currency: 'INR';
    stt_per_hour: 27;
    tts_per_10000_characters: 27;
    local_usage_reference_inr: number | null;
    approved_maximum_reference_inr: 0.9975;
    actual_provider_charge_inr: null;
    actual_modal_charge_usd: null;
    programme_credits_used: null;
  };
}
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0;
const hash = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const TIMINGS = [
  'stt_final_ms',
  'mt_complete_ms',
  'target_tts_first_pcm_ms',
  'target_tts_complete_ms',
  'stt_start_to_target_first_pcm_ms',
  'stt_start_to_target_complete_ms',
] as const;

/** A separate saved follow-up; never overwrites or folds into the original partial trial. */
export function tamilHindiFollowupReport(
  value: unknown = storedEvidence,
): TamilHindiFollowupEvidence | null {
  if (
    !record(value) ||
    value.schema_version !== 1 ||
    value.record_type !== 'controlled_tamil_hindi_followup_evidence'
  )
    return null;
  if (
    value.input_sha256 !== INPUT_HASH ||
    value.source_audio_seconds !== 3.2 ||
    value.source_provenance !== 'existing_standard_voice_clip' ||
    value.source_language !== 'ta' ||
    value.target_language !== 'hi' ||
    value.translation_model !== MODEL ||
    (value.prompt_version !== 'evon-explicit-target-v2' &&
      value.prompt_version !== 'evon-conversational-target-v3') ||
    value.voice_mode !== 'standard'
  )
    return null;
  if (
    value.rtc_tested !== false ||
    value.physical_microphone_tested !== false ||
    value.listener_latency_ms !== null ||
    value.voice_cloning !== false ||
    value.screening_mode !== 'off' ||
    value.automatic_retries !== 0 ||
    value.source_tts_requests !== 0 ||
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
    ![null, 'approval', 'configuration', 'stt', 'mt', 'target_tts', 'cancelled'].includes(
      value.error_stage as string | null,
    )
  )
    return null;
  if (value.error_class !== null && !ERROR_CLASSES.includes(value.error_class as FollowupError))
    return null;
  if (
    !record(value.stt) ||
    value.stt.requested_model !== 'prisma-v3.0' ||
    value.stt.provider_model !== null
  )
    return null;
  if (
    !finite(value.wall_seconds) ||
    value.wall_seconds > 3600 ||
    typeof value.cleanup_complete !== 'boolean' ||
    typeof value.flow_closed !== 'boolean'
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
  if ((used !== null) !== value.flow_closed) return null;
  if (value.status === 'stopped_no_retry' && value.error_class === null) return null;
  if (
    value.status === 'cancelled' &&
    (value.error_class !== 'cancelled' || value.error_stage !== 'cancelled')
  )
    return null;
  if (
    !record(value.timings) ||
    TIMINGS.some(
      (key) =>
        value.timings !== null &&
        (value.timings as Record<string, unknown>)[key] !== null &&
        (!finite((value.timings as Record<string, unknown>)[key]) ||
          ((value.timings as Record<string, unknown>)[key] as number) >
            (value.wall_seconds as number) * 1000 + 1),
    )
  )
    return null;
  const timings = Object.fromEntries(
    TIMINGS.map((key) => [key, (value.timings as Record<string, number | null>)[key]]),
  ) as TamilHindiFollowupEvidence['timings'];
  if (
    value.status === PROVIDER_CHAIN_COMPLETE &&
    (!used ||
      used.stt_connections !== 1 ||
      used.stt_seconds < 1 ||
      used.mt_requests !== 1 ||
      used.tts_requests !== 1 ||
      !value.cleanup_complete ||
      !value.flow_closed ||
      value.error_stage !== null ||
      value.error_class !== null ||
      TIMINGS.some((key) => timings[key] === null))
  )
    return null;
  if (
    (timings.target_tts_first_pcm_ms !== null &&
      timings.target_tts_complete_ms !== null &&
      timings.target_tts_first_pcm_ms > timings.target_tts_complete_ms) ||
    (timings.stt_start_to_target_first_pcm_ms !== null &&
      timings.stt_start_to_target_complete_ms !== null &&
      timings.stt_start_to_target_first_pcm_ms > timings.stt_start_to_target_complete_ms)
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
    value.cost_reference.approved_maximum_reference_inr !== 0.9975 ||
    value.cost_reference.local_usage_reference_inr !== reference ||
    value.cost_reference.actual_provider_charge_inr !== null ||
    value.cost_reference.actual_modal_charge_usd !== null ||
    value.cost_reference.programme_credits_used !== null
  )
    return null;
  return {
    schema_version: 1,
    record_type: 'controlled_tamil_hindi_followup_evidence',
    recorded_on: value.recorded_on,
    source_report_sha256: value.source_report_sha256,
    plan_sha256: value.plan_sha256,
    input_sha256: INPUT_HASH,
    source_audio_seconds: 3.2,
    source_provenance: 'existing_standard_voice_clip',
    source_language: 'ta',
    target_language: 'hi',
    translation_model: MODEL,
    prompt_version: value.prompt_version,
    voice_mode: 'standard',
    status: value.status as TamilHindiFollowupEvidence['status'],
    error_stage: value.error_stage as TamilHindiFollowupEvidence['error_stage'],
    error_class: value.error_class as FollowupError | null,
    stt: { requested_model: 'prisma-v3.0', provider_model: null },
    timings,
    used,
    caps: { ...CAPS },
    wall_seconds: value.wall_seconds,
    cleanup_complete: value.cleanup_complete,
    flow_closed: value.flow_closed,
    meaning_review: 'pending',
    rtc_tested: false,
    physical_microphone_tested: false,
    listener_latency_ms: null,
    voice_cloning: false,
    screening_mode: 'off',
    automatic_retries: 0,
    source_tts_requests: 0,
    cost_reference: {
      currency: 'INR',
      stt_per_hour: 27,
      tts_per_10000_characters: 27,
      local_usage_reference_inr: reference,
      approved_maximum_reference_inr: 0.9975,
      actual_provider_charge_inr: null,
      actual_modal_charge_usd: null,
      programme_credits_used: null,
    },
  };
}
