import { describe, expect, it } from 'vitest';
import type { Metrics, Recap } from '../types/domain';
import { recapServerTiming } from './recapTiming';

const metrics = (patch: Partial<Metrics> = {}): Metrics => ({
  turns: 1,
  stt_ms: 10,
  mt_ms: 20,
  tts_ms: 30,
  total_ms: 60,
  p50_ms: 60,
  p95_ms: 90,
  measurement: 'server_pipeline',
  ...patch,
});
const recap = (patch: Partial<Recap> = {}): Recap =>
  ({
    room: { mode: 'live' },
    localDemo: false,
    metrics: metrics(),
    turns: [{ status: 'complete' }],
    ...patch,
  }) as Recap;

describe('recap server timing evidence', () => {
  it('does not turn an untouched zero aggregate into a latency observation', () => {
    expect(
      recapServerTiming(
        recap({ metrics: metrics({ turns: 0, total_ms: 0, p50_ms: 0, p95_ms: 0 }), turns: [] }),
      ),
    ).toEqual({ measured: false, p50_ms: null, p95_ms: null });
    expect(recapServerTiming(recap({ metrics: null })).measured).toBe(false);
    expect(recapServerTiming(recap({ metrics: undefined })).measured).toBe(false);
  });
  it('does not infer measurements from transcript counts without positive aggregate evidence', () => {
    expect(
      recapServerTiming(recap({ metrics: metrics({ total_ms: 0, p50_ms: 0, p95_ms: 0 }) }))
        .measured,
    ).toBe(false);
    expect(recapServerTiming(recap({ turns: [] })).measured).toBe(false);
    expect(recapServerTiming(recap({ metrics: metrics({ turns: 0 }) })).measured).toBe(false);
  });
  it('keeps valid positive server aggregates, including sub-millisecond values', () => {
    expect(recapServerTiming(recap())).toEqual({ measured: true, p50_ms: 60, p95_ms: 90 });
    expect(
      recapServerTiming(recap({ metrics: metrics({ total_ms: 0.2, p50_ms: 0.1, p95_ms: 0.2 }) }))
        .p50_ms,
    ).toBe(0.1);
  });
  it('excludes raw, scripted and malformed aggregates', () => {
    for (const mode of ['transport', 'demo'] as const)
      expect(recapServerTiming(recap({ room: { mode } as Recap['room'] })).measured).toBe(false);
    expect(recapServerTiming(recap({ localDemo: true })).measured).toBe(false);
    for (const value of [Number.NaN, Number.POSITIVE_INFINITY, -1])
      expect(recapServerTiming(recap({ metrics: metrics({ p50_ms: value }) })).measured).toBe(
        false,
      );
    expect(recapServerTiming(recap({ metrics: metrics({ p95_ms: 10 }) })).measured).toBe(false);
  });
});
