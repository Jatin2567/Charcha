import type { PerformanceSample } from '../types/performance';
import { directionKey, measuredSamples, percentile } from './performance';

/** Compare like-for-like branches. Simulated/forwarded timings never enter these groups. */
export function latencyGroups(samples: PerformanceSample[]) {
  const grouped = new Map<string, PerformanceSample[]>();
  for (const sample of samples) {
    if (sample.measurement !== 'server_first_pcm') continue;
    const key = `${directionKey(sample)}:${sample.input_kind}:${sample.voice_mode}`;
    grouped.set(key, [...(grouped.get(key) ?? []), sample]);
  }
  return [...grouped.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, rows]) => {
      const measured = measuredSamples(rows);
      const stage = (field: 'stt_ms' | 'mt_ms' | 'tts_first_pcm_ms' | 'queue_ms' | 'total_ms') => {
        const values = measured
          .map((row) => row[field])
          .filter(
            (value): value is number => value !== null && Number.isFinite(value) && value >= 0,
          );
        return {
          n: values.length,
          p50_ms: percentile(values, 0.5),
          p95_ms: percentile(values, 0.95),
        };
      };
      return {
        key,
        source_language: rows[0].source_language,
        target_language: rows[0].target_language,
        input_kind: rows[0].input_kind,
        voice_mode: rows[0].voice_mode,
        attempted: rows.length,
        measured: measured.length,
        partial_audio_totals: measured.filter(
          (row) =>
            row.input_kind === 'audio' &&
            (row.stt_ms === null || !Number.isFinite(row.stt_ms) || row.stt_ms < 0),
        ).length,
        errors: rows.filter((row) => row.status === 'error').length,
        cancelled: rows.filter((row) => row.status === 'cancelled').length,
        completed_without_timing:
          rows.filter((row) => row.status === 'complete').length - measured.length,
        queue: stage('queue_ms'),
        recognition: stage('stt_ms'),
        translation: stage('mt_ms'),
        synthesis: stage('tts_first_pcm_ms'),
        total: stage('total_ms'),
      };
    });
}

export function latencyGroupReport(samples: PerformanceSample[]) {
  return {
    schema_version: 1,
    record_type: 'grouped_server_latency',
    boundary: 'queue_to_first_pcm_plus_stt',
    receiver_playback_measured: false,
    note: 'Groups separate direction, input and voice. Only completed server_first_pcm samples with finite totals enter percentiles. Errors, cancellations and missing timings remain visible. Audio totals without STT markers are partial; inspect partial_audio_totals before comparing. Stage percentiles do not add up to total percentiles. This does not establish translation quality.',
    excluded_simulated: samples.filter((row) => row.measurement === 'simulated').length,
    excluded_forwarded: samples.filter((row) => row.measurement === 'source_forwarded').length,
    groups: latencyGroups(samples),
  };
}
