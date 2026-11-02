import matrix from '../data/fiveLanguagePlan.json';
import stage from '../data/fiveLanguageStage.json';

/** Current user-approved compute scope; it is not a provider balance or a test result. */
export const MODAL_TRANSLATION_STAGE = {
  stage_id: stage.id,
  updated_at: '2026-10-31',
  compute_provider: 'Modal',
  compute_access: 'verified' as 'login_required' | 'not_checked' | 'verified',
  approved_compute_ceiling_usd: stage.modal_usd_limit,
  approved_max_flows: stage.flow_limit,
  initial_directions: stage.routes.map(([source_language, target_language]) => ({
    source_language,
    target_language,
  })),
  voice_mode: 'standard',
  screening_mode: 'off',
  voice_cloning: 'deferred',
  remaining_compute_credit_usd: null,
  actual_compute_cost_usd: null,
} as const;

/** Curated export: the older GCP budget stays in its source proposal, not this current plan. */
export function conferenceTestPlan() {
  return {
    schema_version: 1,
    record_type: 'conference_translation_test_plan',
    current_stage: {
      ...MODAL_TRANSLATION_STAGE,
      initial_directions: MODAL_TRANSLATION_STAGE.initial_directions.map((route) => ({ ...route })),
    },
    plan_only: true,
    source_matrix_id: matrix.plan_id,
    source_matrix_sha256: matrix.plan_sha256,
    language_codes: [...matrix.language_codes],
    languages: matrix.languages.map(({ code, name, standard_voice }) => ({
      code,
      name,
      standard_voice,
      live_acceptance: 'not_verified',
    })),
    planned_directed_pairs: matrix.planned_directed_pairs,
    planned_pairwise_observations: matrix.planned_observations,
    pairwise_participants: 2,
    conference_participants_target: 5,
    conference_acceptance: 'pending_real_devices',
    routes: matrix.routes.map((route) => ({
      route_id: route.route_id,
      source_language: route.source_language,
      target_language: route.target_language,
      source_text: route.source_text,
      expected_meaning: [...route.expected_meaning],
      source_reference_status: route.source_reference_status,
      semantic_result: 'not_tested',
      standard_voice: route.voice.name,
    })),
    planned_setup_states: ['new_route_model_already_loaded', 'warm_repeat_1', 'warm_repeat_2'],
    model_cold_start: 'Record separately; a newly joined route is not GPU/model startup.',
    measurement_boundaries: {
      server: 'Queue to first server PCM plus the available STT processing-to-transcript proxy.',
      receiver: 'Source phrase end to listener output onset in one shared-clock recording.',
      network: 'WebRTC round trip, jitter, buffering and packet loss; not translation delay.',
    },
    reporting: {
      actual_observations: null,
      actual_provider_cost: null,
      provider_calls_from_this_page: 0,
      automatic_execution: false,
      cold_warm_classification: 'Record observed setup; do not infer it from trial order.',
      failed_trials: 'Retain failures, cancellations, missing markers and unattempted routes.',
      speech_cost: 'Gnani STT/TTS limits and costs are separate from Modal compute.',
      hosting: 'Use local hosting first; GCP hosting is conditional on deployment needs.',
      note: 'A saved plan is not a live result. Five language choices do not establish five-device acceptance.',
    },
  };
}
