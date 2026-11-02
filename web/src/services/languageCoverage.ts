import { LANGUAGES, SCRIPTED_LANGUAGE_CODES } from '../types/domain';
import type { Language } from '../types/domain';
import batch from '../data/fiveLanguageStageResults.json';

export function batchDelivery(source: Language, target: Language) {
  if (source === target) return 'Original';
  const row =
    batch.recorded && batch.routes.find((r) => r.source === source && r.target === target);
  if (row && row.status === 'receiver_decoded') return 'Received';
  if (row && row.status === 'failed') return 'Failed';
  return '—';
}

export const LANGUAGE_REVIEW_STATUS = 'not_tested' as const;
/** A review plan, never a generated translation or provider-quality result. */
export const languageRoutes = () =>
  LANGUAGES.flatMap((source) =>
    LANGUAGES.filter((target) => target.code !== source.code).map((target) => ({
      source_language: source.code,
      target_language: target.code,
      status: LANGUAGE_REVIEW_STATUS,
    })),
  );
export const sourceRouting = (source: Language) =>
  languageRoutes().filter((route) => route.source_language === source);
export const languageRoutingPlan = () => ({
  record_type: 'offline_language_routing_plan',
  languages: LANGUAGES.map(({ code, name, native }) => ({ code, name, native })),
  directed_route_count: LANGUAGES.length * (LANGUAGES.length - 1),
  scripted_example_languages: [...SCRIPTED_LANGUAGE_CODES],
  baseline_directed_route_count:
    SCRIPTED_LANGUAGE_CODES.length * (SCRIPTED_LANGUAGE_CODES.length - 1),
  routes: languageRoutes(),
  same_language_speech:
    'Forward original audio through the agent; no MT or TTS branch for microphone speech.',
  distinct_target_languages:
    'One translation/synthesis branch per unique listener language, shared by listeners of that language.',
  approval_granted: false,
  provider_requests_made: 0,
  note: 'This worksheet lists directions for human listening review. The five-language batch has separate recorded delivery results on the Performance page.',
});
