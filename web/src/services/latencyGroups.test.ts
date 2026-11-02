import { describe, expect, it } from 'vitest';
import type { PerformanceSample } from '../types/performance';
import { latencyGroups, latencyGroupReport } from './latencyGroups';

const sample = (patch: Partial<PerformanceSample> = {}): PerformanceSample => ({
  id: 'one',
  utterance_id: 'one',
  source_language: 'hi',
  target_language: 'ta',
  input_kind: 'audio',
  voice_mode: 'standard',
  status: 'complete',
  measurement: 'server_first_pcm',
  queue_ms: 0,
  stt_ms: 100,
  mt_ms: 200,
  tts_first_pcm_ms: 300,
  total_ms: 600,
  created_at: '2026-10-28T00:00:00Z',
  ...patch,
});

describe('like-for-like latency groups', () => {
  it('separates typed text, microphone, voice and direction without mixing faster text results', () => {
    const groups = latencyGroups([
      sample(),
      sample({ input_kind: 'text', stt_ms: null, total_ms: 200 }),
      sample({ voice_mode: 'cloned', total_ms: 900 }),
      sample({ source_language: 'ta', target_language: 'hi', total_ms: 800 }),
    ]);
    expect(groups).toHaveLength(4);
    expect(groups.find((g) => g.key === 'hi:ta:audio:standard')?.total.p50_ms).toBe(600);
    expect(groups.find((g) => g.input_kind === 'text')?.recognition).toEqual({
      n: 0,
      p50_ms: null,
      p95_ms: null,
    });
  });
  it('excludes fixtures but retains failed, cancelled and invalid measured attempts', () => {
    const report = latencyGroupReport([
      sample(),
      sample({ measurement: 'simulated', total_ms: 1 }),
      sample({ measurement: 'source_forwarded', total_ms: 2 }),
      sample({ status: 'error', total_ms: 3 }),
      sample({ status: 'cancelled', total_ms: 4 }),
      sample({ total_ms: NaN }),
      sample({ total_ms: null }),
    ]);
    expect(report).toMatchObject({ excluded_simulated: 1, excluded_forwarded: 1 });
    expect(report.groups[0]).toMatchObject({
      attempted: 5,
      measured: 1,
      errors: 1,
      cancelled: 1,
      completed_without_timing: 2,
      total: { n: 1, p50_ms: 600, p95_ms: 600 },
    });
  });
  it('keeps failed-only groups with no invented latency and safely allowlists exports', () => {
    const report = latencyGroupReport([
      {
        ...sample({ status: 'error' }),
        secret: 'never-export',
        text: 'private',
      } as PerformanceSample,
    ]);
    expect(report.groups[0].total).toEqual({ n: 0, p50_ms: null, p95_ms: null });
    expect(JSON.stringify(report)).not.toMatch(/never-export|private/);
    expect(report.receiver_playback_measured).toBe(false);
    expect(latencyGroups([])).toEqual([]);
  });
  it('filters invalid stage values while preserving genuine zero duration', () => {
    const group = latencyGroups([sample({ mt_ms: Infinity }), sample({ stt_ms: -1, mt_ms: 0 })])[0];
    expect(group.translation).toEqual({ n: 1, p50_ms: 0, p95_ms: 0 });
    expect(group.recognition.n).toBe(1);
    expect(group.partial_audio_totals).toBe(1);
  });
});
