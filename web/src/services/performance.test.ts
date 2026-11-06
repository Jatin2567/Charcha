import { describe, expect, it } from 'vitest';
import type { PerformanceSample } from '../types/performance';
import {
  DEFAULT_FILTER,
  csvCell,
  emptyPerformance,
  filterSamples,
  percentile,
  performanceCsv,
  sanitizedReport,
  summarize,
} from './performance';

const sample = (patch: Partial<PerformanceSample> = {}): PerformanceSample => ({
  id: 'branch-1',
  utterance_id: 'utterance-1',
  source_language: 'hi',
  target_language: 'ta',
  input_kind: 'audio',
  voice_mode: 'standard',
  status: 'complete',
  measurement: 'server_first_pcm',
  queue_ms: 10,
  stt_ms: 120,
  mt_ms: 200,
  tts_first_pcm_ms: 300,
  total_ms: 630,
  created_at: '2026-10-24T01:02:03Z',
  ...patch,
});

describe('performance evidence', () => {
  it('returns no measurement for empty or inapplicable samples rather than zero milliseconds', () => {
    expect(percentile([], 0.5)).toBeNull();
    expect(percentile([null, NaN, Infinity, -1], 0.95)).toBeNull();
    expect(summarize([]).p50_ms).toBeNull();
    expect(percentile([0], 0.5)).toBe(0);
  });
  it('uses nearest-rank percentiles without mutating the input', () => {
    const values = [300, 100, 400, 200];
    expect(percentile(values, 0.5)).toBe(200);
    expect(percentile(values, 0.95)).toBe(400);
    expect(values).toEqual([300, 100, 400, 200]);
  });
  it('excludes scripted, forwarded, failed and cancelled branches from live percentiles', () => {
    const summary = summarize([
      sample({ total_ms: 700 }),
      sample({ id: 'two', total_ms: 900 }),
      sample({ id: 'demo', measurement: 'simulated', total_ms: 0 }),
      sample({ id: 'forward', measurement: 'source_forwarded', total_ms: 1 }),
      sample({ id: 'failed', status: 'error', total_ms: 1 }),
      sample({ id: 'cancel', status: 'cancelled', total_ms: 1 }),
      sample({ id: 'missing', total_ms: null }),
    ]);
    expect(summary).toMatchObject({
      sample_count: 7,
      success_count: 5,
      live_sample_count: 2,
      simulated_count: 1,
      forwarded_count: 1,
      error_count: 1,
      cancelled_count: 1,
      p50_ms: 700,
      p95_ms: 900,
    });
  });
  it('separates input source, direction and outcome before computing summary', () => {
    const rows = [
      sample(),
      sample({ id: 'typed', input_kind: 'text' }),
      sample({ id: 'bengali', source_language: 'bn', total_ms: 2000 }),
      sample({ id: 'error', status: 'error' }),
    ];
    const result = filterSamples(rows, {
      direction: 'hi:ta',
      input: 'audio',
      voice: 'all',
      status: 'complete',
    });
    expect(result.map((entry) => entry.id)).toEqual(['branch-1']);
    expect(summarize(result).by_direction).toEqual([
      expect.objectContaining({
        source_language: 'hi',
        target_language: 'ta',
        p50_ms: 630,
        sample_count: 1,
      }),
    ]);
  });
  it('keeps failed branch counts even when the direction has no usable timings', () => {
    const summary = summarize([sample({ status: 'error', error_stage: 'mt', total_ms: null })]);
    expect(summary.by_direction[0]).toMatchObject({
      error_count: 1,
      p50_ms: null,
      p95_ms: null,
      live_sample_count: 0,
    });
  });
  it('separates standard and cloned synthesis without changing total sampling rules', () => {
    const rows = [
      sample({ total_ms: 100 }),
      sample({ id: 'clone', voice_mode: 'cloned', total_ms: 900 }),
    ];
    const selected = filterSamples(rows, { ...DEFAULT_FILTER, voice: 'cloned' });
    expect(selected.map((entry) => entry.id)).toEqual(['clone']);
    expect(summarize(selected).p50_ms).toBe(900);
  });
});

describe('safe performance exports', () => {
  it('exports an explicit metadata allowlist with no accidental fields from the API', () => {
    const report = {
      ...emptyPerformance('private-room', 'live'),
      session_token: 'secret',
      transcript: 'private conversation',
      samples: [
        {
          ...sample(),
          participant_name: 'Private Name',
          text: 'Confidential',
          voice_embedding: [1, 2],
        },
      ],
      configuration: { GNANI_API_KEY: 'secret' },
    };
    const exported = JSON.stringify(sanitizedReport(report, DEFAULT_FILTER));
    for (const forbidden of [
      'secret',
      'Confidential',
      'private-room',
      'Private Name',
      'voice_embedding',
      'GNANI_API_KEY',
    ])
      expect(exported).not.toContain(forbidden);
    expect(JSON.parse(exported).samples[0].total_ms).toBe(630);
    expect(JSON.parse(exported).measurement.receiver_playback_measured).toBe(false);
  });
  it('exports only the current filters and recalculates their percentiles', () => {
    const report = {
      ...emptyPerformance('room', 'live'),
      samples: [sample(), sample({ id: 'text', input_kind: 'text', total_ms: 100 })],
    };
    const exported = sanitizedReport(report, { ...DEFAULT_FILTER, input: 'audio' });
    expect(exported.samples).toHaveLength(1);
    expect(exported.summary.p50_ms).toBe(630);
  });
  it('quotes delimiters, double quotes and line breaks and neutralizes spreadsheet formulas', () => {
    expect(csvCell('a,"b"\nc')).toBe('"a,""b""\nc"');
    expect(csvCell(' =HYPERLINK("bad")')).toBe('"\' =HYPERLINK(""bad"")"');
    expect(csvCell('@SUM(1,2)')).toBe('"\'@SUM(1,2)"');
    expect(csvCell(null)).toBe('""');
  });
  it('applies CSV protections to samples and retains typed STT as blank', () => {
    const report = {
      ...emptyPerformance('room', 'live'),
      samples: [sample({ id: '=1+1', input_kind: 'text', stt_ms: null })],
    };
    const csv = performanceCsv(report, DEFAULT_FILTER);
    expect(csv).toContain('"\'=1+1"');
    const [header, row] = csv.split('\r\n').map((line) => line.split(','));
    expect(row[header.indexOf('"stt_ms"')]).toBe('""');
    expect(row[header.indexOf('"queue_ms"')]).toBe('"10"');
    expect(row[header.indexOf('"mt_ms"')]).toBe('"200"');
    expect(csv.split('\r\n')).toHaveLength(2);
  });
});
