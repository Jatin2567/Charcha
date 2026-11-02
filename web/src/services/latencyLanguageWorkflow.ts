import storedPlan from '../data/latencyLanguagePlan.json';
import { LANGUAGES } from '../types/domain';
import type { Language } from '../types/domain';

const CATEGORY = ['ordinary', 'negation', 'names', 'numbers'] as const;
export type LatencyCaseCategory = (typeof CATEGORY)[number];
const REASONS = [
  'measurement_contract_not_eligible',
  'shared_recording_boundary_required',
  'live_provider_required',
  'physical_or_electrical_capture_required',
  'capture_attestation_required',
  'meaning_review_pending',
  'annotation_review_pending',
  'standard_voice_stage_required',
  'observation_identity_required',
  'invalid_sample_clock_measurement',
  'latency_sample_indices_disagree',
  'overlap_requires_review',
  'attempt_not_complete',
  'unknown_observation_condition',
  'duplicate_observation',
  'minimum_warm_attempts_not_met',
  'all_warm_attempts_must_complete',
  'all_warm_attempts_must_qualify',
  'p50_not_strictly_under_goal',
  'p95_not_strictly_under_goal',
] as const;
export type LatencyGateReason = (typeof REASONS)[number];
export interface LatencyGate {
  source_language: 'hi' | 'ta';
  target_language: 'hi' | 'ta';
  passed: boolean;
  status: 'passed_for_next_test_review' | 'blocked';
  reason_codes: LatencyGateReason[];
  counts: {
    warm_attempts: number;
    warm_complete: number;
    warm_qualifying: number;
    warm_failures: number;
    first_route_attempts: number;
    duplicate_observations: number;
    overlap_observations: number;
  };
  metrics: {
    p50_ms: number | null;
    p95_ms: number | null;
    warm_failure_rate: number | null;
    basis: 'qualifying_warm_attempts_only';
    first_route_ms: number | null;
  };
  observed_warm_latency_ms: number[];
  approval_granted: false;
  physical_provenance: 'operator_attested_not_cryptographic_proof';
}
export interface LatencyWorkflowReference {
  schema_version: 1;
  record_type: 'latency_language_workflow_reference';
  source_plan_sha256: string;
  plan_only: true;
  provider_calls_made: 0;
  approval_granted: false;
  full_matrix_authorized: false;
  full_matrix_eligible_for_test_review: boolean;
  language_count: 10;
  planned_directed_pairs: 90;
  optional_same_language_routes: 10;
  draft_case_count: 40;
  languages: {
    code: Language;
    name: string;
    locale: string;
    standard_voice: string;
    catalog_status: 'documented';
    live_quality: 'not_assessed_by_this_plan';
    source_review: 'pending';
    meaning_review: 'pending';
    physical_device_acceptance: 'pending';
  }[];
  gates: { hi_to_ta: LatencyGate; ta_to_hi: LatencyGate };
  gate_policy: {
    minimum_warm_attempts: 10;
    all_warm_attempts_complete: true;
    maximum_warm_failure_rate: 0;
    p50_strictly_under_ms: 2000;
    p95_strictly_under_ms: 2000;
    percentile_method: 'nearest_rank';
    clock: 'single_recording_sample_index';
    boundary: 'source_speech_end_to_listener_output';
    provider_kind: 'live';
    voice_mode: 'standard';
    meaning_review_required: true;
    annotations_review_required: true;
    capture_attestation_required: true;
    capture_kinds: [
      'acoustic_single_channel',
      'acoustic_two_channel',
      'electrical_loopback_two_channel',
    ];
  };
  draft_cases: {
    case_id: string;
    source_language: Language;
    category: LatencyCaseCategory;
    source_text: string;
    expected_meaning: string[];
    review_focus: string[];
    source_reference_status: 'draft_pending_fluent_review';
    target_reference: null;
    meaning_acceptance: 'pending';
  }[];
  routes: {
    route_id: string;
    source_language: Language;
    target_language: Language;
    eligible_for_test_review: boolean;
    approval_granted: false;
    automatic_execution: false;
    draft_case_ids: string[];
  }[];
}
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const count = (value: unknown): value is number =>
  Number.isInteger(value) && (value as number) >= 0 && (value as number) <= 1000;
const duration = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 3_600_000;
const texts = (value: unknown): value is string[] =>
  Array.isArray(value) &&
  value.length <= 12 &&
  value.every(
    (row) =>
      typeof row === 'string' &&
      row.length <= 500 &&
      !/vach_[A-Za-z0-9_-]+|Bearer\s+\S+|https?:\/\//i.test(row),
  );

function gate(value: unknown, source: 'hi' | 'ta', target: 'hi' | 'ta'): LatencyGate | null {
  if (
    !record(value) ||
    value.source_language !== source ||
    value.target_language !== target ||
    typeof value.passed !== 'boolean' ||
    value.approval_granted !== false ||
    value.physical_provenance !== 'operator_attested_not_cryptographic_proof' ||
    !record(value.counts) ||
    !record(value.metrics) ||
    !Array.isArray(value.reason_codes) ||
    value.reason_codes.some((reason) => !REASONS.includes(reason as LatencyGateReason)) ||
    !Array.isArray(value.observed_warm_latency_ms) ||
    value.observed_warm_latency_ms.some((row) => !duration(row))
  )
    return null;
  const keys = [
    'warm_attempts',
    'warm_complete',
    'warm_qualifying',
    'warm_failures',
    'first_route_attempts',
    'duplicate_observations',
    'overlap_observations',
  ] as const;
  if (keys.some((key) => !count((value.counts as Record<string, unknown>)[key]))) return null;
  const counts = Object.fromEntries(
    keys.map((key) => [key, (value.counts as Record<string, number>)[key]]),
  ) as LatencyGate['counts'];
  if (
    counts.warm_complete + counts.warm_failures !== counts.warm_attempts ||
    counts.warm_qualifying > counts.warm_complete
  )
    return null;
  const raw = value.metrics;
  if (
    raw.basis !== 'qualifying_warm_attempts_only' ||
    ['p50_ms', 'p95_ms', 'first_route_ms'].some(
      (key) => raw[key] !== null && (!duration(raw[key]) || (raw[key] as number) < 0),
    ) ||
    raw.warm_failure_rate !==
      (counts.warm_attempts ? counts.warm_failures / counts.warm_attempts : null)
  )
    return null;
  if (
    value.passed &&
    (value.status !== 'passed_for_next_test_review' ||
      value.reason_codes.length !== 0 ||
      counts.warm_attempts < 10 ||
      counts.warm_complete !== counts.warm_attempts ||
      counts.warm_qualifying !== counts.warm_attempts ||
      counts.warm_failures !== 0 ||
      counts.duplicate_observations !== 0 ||
      counts.overlap_observations !== 0 ||
      !duration(raw.p50_ms) ||
      raw.p50_ms < 0 ||
      raw.p50_ms >= 2000 ||
      !duration(raw.p95_ms) ||
      raw.p95_ms < 0 ||
      raw.p95_ms >= 2000)
  )
    return null;
  if (!value.passed && (value.status !== 'blocked' || value.reason_codes.length === 0)) return null;
  return {
    source_language: source,
    target_language: target,
    passed: value.passed,
    status: value.passed ? 'passed_for_next_test_review' : 'blocked',
    reason_codes: [...value.reason_codes] as LatencyGateReason[],
    counts,
    metrics: {
      p50_ms: raw.p50_ms as number | null,
      p95_ms: raw.p95_ms as number | null,
      warm_failure_rate: raw.warm_failure_rate as number | null,
      basis: 'qualifying_warm_attempts_only',
      first_route_ms: raw.first_route_ms as number | null,
    },
    observed_warm_latency_ms: [...value.observed_warm_latency_ms] as number[],
    approval_granted: false,
    physical_provenance: 'operator_attested_not_cryptographic_proof',
  };
}

/** A read-only view of the offline physical-gated plan, never permission to execute it. */
export function latencyWorkflowReference(
  value: unknown = storedPlan,
): LatencyWorkflowReference | null {
  if (
    !record(value) ||
    value.schema_version !== 1 ||
    value.record_type !== 'latency_language_workflow_plan' ||
    value.plan_only !== true ||
    value.provider_calls_made !== 0 ||
    value.approval_granted !== false ||
    value.automatic_matrix_runner !== false ||
    value.full_matrix_authorized !== false ||
    value.language_count !== 10 ||
    value.planned_directed_pairs !== 90 ||
    value.optional_same_language_routes !== 10 ||
    value.draft_case_count !== 40 ||
    typeof value.plan_sha256 !== 'string' ||
    !/^[a-f0-9]{64}$/.test(value.plan_sha256) ||
    !record(value.gates) ||
    !record(value.gate_policy) ||
    !Array.isArray(value.languages) ||
    value.languages.length !== 10 ||
    !Array.isArray(value.draft_cases) ||
    value.draft_cases.length !== 40 ||
    !Array.isArray(value.routes) ||
    value.routes.length !== 90
  )
    return null;
  const policy = {
    minimum_warm_attempts: 10,
    all_warm_attempts_complete: true,
    maximum_warm_failure_rate: 0,
    p50_strictly_under_ms: 2000,
    p95_strictly_under_ms: 2000,
    percentile_method: 'nearest_rank',
    clock: 'single_recording_sample_index',
    boundary: 'source_speech_end_to_listener_output',
    provider_kind: 'live',
    voice_mode: 'standard',
    meaning_review_required: true,
    annotations_review_required: true,
    capture_attestation_required: true,
  } as const;
  if (
    Object.entries(policy).some(
      ([key, expected]) => (value.gate_policy as Record<string, unknown>)[key] !== expected,
    )
  )
    return null;
  const kinds = value.gate_policy.capture_kinds;
  if (
    !Array.isArray(kinds) ||
    kinds.length !== 3 ||
    kinds[0] !== 'acoustic_single_channel' ||
    kinds[1] !== 'acoustic_two_channel' ||
    kinds[2] !== 'electrical_loopback_two_channel'
  )
    return null;
  const forward = gate(value.gates.hi_to_ta, 'hi', 'ta'),
    reverse = gate(value.gates.ta_to_hi, 'ta', 'hi');
  if (
    !forward ||
    !reverse ||
    value.full_matrix_eligible_for_test_review !== (forward.passed && reverse.passed)
  )
    return null;
  const languages: LatencyWorkflowReference['languages'] = [];
  for (const expected of LANGUAGES) {
    const matches = value.languages.filter((row) => record(row) && row.code === expected.code);
    if (matches.length !== 1 || !record(matches[0])) return null;
    const row = matches[0];
    if (
      typeof row.standard_voice !== 'string' ||
      !/^[A-Za-z][A-Za-z0-9 -]{0,40}$/.test(row.standard_voice) ||
      row.locale !== `${expected.code}-IN` ||
      row.source_review !== 'pending' ||
      row.meaning_review !== 'pending' ||
      row.physical_device_acceptance !== 'pending' ||
      !record(row.providers) ||
      ['stt', 'mt', 'tts'].some(
        (key) =>
          !record((row.providers as Record<string, unknown>)[key]) ||
          (row.providers as Record<string, Record<string, unknown>>)[key].catalog_status !==
            'documented' ||
          (row.providers as Record<string, Record<string, unknown>>)[key]
            .live_language_acceptance !== 'not_assessed_by_this_plan',
      )
    )
      return null;
    languages.push({
      code: expected.code,
      name: expected.name,
      locale: `${expected.code}-IN`,
      standard_voice: row.standard_voice,
      catalog_status: 'documented',
      live_quality: 'not_assessed_by_this_plan',
      source_review: 'pending',
      meaning_review: 'pending',
      physical_device_acceptance: 'pending',
    });
  }
  const drafts: LatencyWorkflowReference['draft_cases'] = [];
  const ids = new Set<string>();
  for (const row of value.draft_cases) {
    if (
      !record(row) ||
      !LANGUAGES.some((language) => language.code === row.source_language) ||
      !CATEGORY.includes(row.category as LatencyCaseCategory) ||
      row.case_id !== `${row.source_language}-${row.category}` ||
      ids.has(String(row.case_id)) ||
      typeof row.source_text !== 'string' ||
      !row.source_text.trim() ||
      row.source_text.length > 300 ||
      /vach_[A-Za-z0-9_-]+|Bearer\s+\S+/i.test(row.source_text) ||
      !texts(row.expected_meaning) ||
      !texts(row.review_focus) ||
      row.source_reference_status !== 'draft_pending_fluent_review' ||
      row.target_reference !== null ||
      row.meaning_acceptance !== 'pending'
    )
      return null;
    ids.add(String(row.case_id));
    drafts.push({
      case_id: String(row.case_id),
      source_language: row.source_language as Language,
      category: row.category as LatencyCaseCategory,
      source_text: row.source_text,
      expected_meaning: [...row.expected_meaning],
      review_focus: [...row.review_focus],
      source_reference_status: 'draft_pending_fluent_review',
      target_reference: null,
      meaning_acceptance: 'pending',
    });
  }
  const pairs = new Set<string>();
  const routes: LatencyWorkflowReference['routes'] = [];
  for (const row of value.routes) {
    if (
      !record(row) ||
      !LANGUAGES.some((language) => language.code === row.source_language) ||
      !LANGUAGES.some((language) => language.code === row.target_language) ||
      row.source_language === row.target_language ||
      row.route_id !== `${row.source_language}-${row.target_language}` ||
      pairs.has(String(row.route_id)) ||
      row.approval_granted !== false ||
      row.automatic_execution !== false
    )
      return null;
    const eligible =
      row.source_language === 'hi' && row.target_language === 'ta'
        ? true
        : row.source_language === 'ta' && row.target_language === 'hi'
          ? forward.passed
          : forward.passed && reverse.passed;
    if (row.eligible_for_test_review !== eligible) return null;
    pairs.add(String(row.route_id));
    routes.push({
      route_id: String(row.route_id),
      source_language: row.source_language as Language,
      target_language: row.target_language as Language,
      eligible_for_test_review: eligible,
      approval_granted: false,
      automatic_execution: false,
      draft_case_ids: drafts
        .filter((entry) => entry.source_language === row.source_language)
        .map((entry) => entry.case_id),
    });
  }
  return {
    schema_version: 1,
    record_type: 'latency_language_workflow_reference',
    source_plan_sha256: value.plan_sha256,
    plan_only: true,
    provider_calls_made: 0,
    approval_granted: false,
    full_matrix_authorized: false,
    full_matrix_eligible_for_test_review: forward.passed && reverse.passed,
    language_count: 10,
    planned_directed_pairs: 90,
    optional_same_language_routes: 10,
    draft_case_count: 40,
    languages,
    gates: { hi_to_ta: forward, ta_to_hi: reverse },
    gate_policy: {
      ...policy,
      capture_kinds: [
        'acoustic_single_channel',
        'acoustic_two_channel',
        'electrical_loopback_two_channel',
      ],
    },
    draft_cases: drafts,
    routes,
  };
}
