import { describe, expect, it } from 'vitest';
import { receiverProbeReport } from './receiverMetrics';
import { PROBE_MEASUREMENT } from './audioProbe';

const fixture = () => ({
  room_code: 'private-room',
  generated_at: '2026-10-30T10:00:00Z',
  measurement: {
    boundary: PROBE_MEASUREMENT,
    clock: 'single_browser_monotonic',
    client_reported: true,
    physical_speaker_output_measured: false,
    translation_end_to_end_measured: false,
  },
  summary: { p50_ms: 999999, sample_count: 999999 },
  samples: [
    {
      probe_id: 'private-probe-1',
      listener_id: 'self',
      measurement: PROBE_MEASUREMENT,
      status: 'detected',
      elapsed_ms: 200,
      poll_interval_ms: 100,
      created_at: '2026-10-30T09:00:00Z',
    },
    {
      probe_id: 'private-probe-2',
      listener_id: 'self',
      measurement: PROBE_MEASUREMENT,
      status: 'timeout',
      elapsed_ms: null,
      poll_interval_ms: 100,
      created_at: '2026-10-30T09:01:00Z',
    },
    {
      probe_id: 'private-probe-3',
      listener_id: 'other',
      measurement: PROBE_MEASUREMENT,
      status: 'detected',
      elapsed_ms: 9000,
      poll_interval_ms: 100,
      created_at: '2026-10-30T09:02:00Z',
    },
  ],
});

describe('receiver-only audio metrics', () => {
  it('recomputes this listener’s measured latency while retaining a failed attempt', () => {
    const report = receiverProbeReport(fixture(), 'self')!;
    expect(report.summary).toEqual({
      attempted: 2,
      detected: 1,
      failed: 1,
      cancelled: 0,
      p50_ms: 200,
      p95_ms: 200,
    });
    expect(report.samples).toHaveLength(2);
    expect(report.measurement.translation_end_to_end_measured).toBe(false);
  });

  it('keeps empty or all-failed receiver measurements unknown instead of inventing zero', () => {
    expect(receiverProbeReport(fixture(), 'not-in-room')?.summary).toMatchObject({
      attempted: 0,
      p50_ms: null,
      p95_ms: null,
    });
    const raw = fixture();
    raw.samples = raw.samples.filter((row) => row.status === 'timeout');
    expect(receiverProbeReport(raw, 'self')?.summary).toMatchObject({
      attempted: 1,
      failed: 1,
      detected: 0,
      p50_ms: null,
    });
  });

  it('strips room/listener/probe identifiers, tokens and unexpected data from the export', () => {
    const raw = { ...fixture(), session_token: 'private-token', transcript: 'private-words' };
    const output = JSON.stringify(receiverProbeReport(raw, 'self'));
    expect(output).not.toMatch(/private-|listener_id|probe_id|room_code|session_token|transcript/);
  });

  it.each([NaN, Infinity, -1, '100'])('rejects an invalid detected timing %s', (elapsed) => {
    const raw = fixture() as unknown as { samples: Record<string, unknown>[] };
    raw.samples[0].elapsed_ms = elapsed;
    expect(receiverProbeReport(raw, 'self')).toBeNull();
  });

  it('rejects duplicated observations and claims of physical or translated playback timing', () => {
    const duplicate = fixture();
    duplicate.samples.push({ ...duplicate.samples[0] });
    expect(receiverProbeReport(duplicate, 'self')).toBeNull();
    for (const field of ['physical_speaker_output_measured', 'translation_end_to_end_measured']) {
      const raw = fixture() as unknown as { measurement: Record<string, unknown> };
      raw.measurement[field] = true;
      expect(receiverProbeReport(raw, 'self')).toBeNull();
    }
  });

  it('retains cancelled outcomes without putting them into timing percentiles', () => {
    const raw = fixture();
    raw.samples[1].status = 'cancelled';
    expect(receiverProbeReport(raw, 'self')?.summary).toMatchObject({
      attempted: 2,
      cancelled: 1,
      failed: 0,
      p50_ms: 200,
    });
    raw.samples[1].elapsed_ms = 100;
    expect(receiverProbeReport(raw, 'self')).toBeNull();
  });
});
