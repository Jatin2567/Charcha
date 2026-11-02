import type { Metrics, Recap } from '../types/domain';

/** Legacy room aggregates use zero as their empty default, not a measured observation. */
export function recapServerTiming(recap: Pick<Recap, 'room' | 'localDemo' | 'metrics' | 'turns'>) {
  const metrics = (recap.metrics ?? null) as (Metrics & { simulated?: boolean }) | null;
  const positive = (value: unknown): value is number =>
    typeof value === 'number' && Number.isFinite(value) && value > 0;
  const measured =
    recap.room.mode === 'live' &&
    !recap.localDemo &&
    metrics !== null &&
    metrics.simulated !== true &&
    metrics.measurement === 'server_pipeline' &&
    Number.isInteger(metrics.turns) &&
    metrics.turns > 0 &&
    recap.turns.length > 0 &&
    positive(metrics.total_ms) &&
    positive(metrics.p50_ms) &&
    positive(metrics.p95_ms) &&
    metrics.p95_ms >= metrics.p50_ms;
  return {
    measured,
    p50_ms: measured ? metrics.p50_ms : null,
    p95_ms: measured ? metrics.p95_ms : null,
  };
}
