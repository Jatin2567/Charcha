import { describe, expect, it } from 'vitest';
import { coldStartReduction, coldStartReport, summarizeColdStarts } from './coldStartComparison';

const group = (runs: unknown[]) =>
  coldStartReport({ baseline: { label: 'Before', runs } }).baseline;
const direction = (ms: unknown) => ({
  route: 'peer 1 → peer 2',
  capture_to_first_received_pcm_ms: ms,
});

describe('saved local cold-start evidence', () => {
  it('preserves failed runs but excludes their timings from the comparison', () => {
    const source = group([
      { run_id: 'before-1', passed: true, directions: [direction(12000), direction(4000)] },
      {
        run_id: 'before-2',
        passed: false,
        directions: [direction(10)],
        notes: 'Mute recovery failed',
      },
      { run_id: 'before-3', directions: [direction(5)] },
    ]);
    expect(source.runs).toHaveLength(3);
    expect(summarizeColdStarts(source)).toEqual({
      sample_count: 2,
      median_ms: 8000,
      min_ms: 4000,
      max_ms: 12000,
      passed_runs: 1,
      failed_runs: 1,
      unrecorded_runs: 1,
      run_count: 3,
    });
    expect(source.runs[1].notes).toBe('Mute recovery failed');
  });

  it('never turns missing, zero or invalid measurements into an improvement', () => {
    const source = group([
      {
        passed: true,
        directions: [
          direction(null),
          direction(0),
          direction(-1),
          direction(NaN),
          direction(Infinity),
          direction('200'),
        ],
      },
    ]);
    const result = summarizeColdStarts(source);
    expect(result.sample_count).toBe(0);
    expect(result.median_ms).toBeNull();
    expect(result.min_ms).toBeNull();
    expect(result.max_ms).toBeNull();
    expect(coldStartReduction(1000, result.median_ms)).toBeNull();
    expect(coldStartReduction(0, 200)).toBeNull();
    expect(coldStartReduction(1000, NaN)).toBeNull();
    expect(coldStartReduction(Infinity, 200)).toBeNull();
  });

  it('shows improvement or regression without inventing tail percentiles', () => {
    const result = summarizeColdStarts(
      group([{ passed: true, directions: [direction(120), direction(90), direction(500)] }]),
    );
    expect(result.median_ms).toBe(120);
    expect(result).not.toHaveProperty('p95_ms');
    expect(coldStartReduction(1000, 250)).toBe(75);
    expect(coldStartReduction(250, 1000)).toBe(-300);
  });

  it('exports only the public evidence contract, without runtime identities or secrets', () => {
    const report = coldStartReport({
      token: 'private-token',
      room_code: 'private-room',
      recorded_at: '2026-10-28',
      boundary: 'One monotonic process clock',
      baseline: {
        label: 'Before',
        session_token: 'private-session',
        runs: [
          {
            run_id: 'before-1',
            passed: true,
            participant_id: 'private-participant',
            directions: [{ ...direction(250), credentials: 'private-key' }],
            mute_request_to_receiver_track_detached_ms: 120,
          },
        ],
      },
      historical: { label: 'Prior incident', token: 'private-history', runs: [{ passed: true, run_id: 'incident-1', directions: [{ ...direction(12000), speaker_id: 'private-speaker' }] }] },
      fix_summary: ['Bounded startup buffering'],
      limitations: ['Synthetic signals only'],
    });
    expect(JSON.stringify(report)).not.toContain('private-');
    expect(report.baseline.runs[0].mute_request_to_receiver_track_detached_ms).toBe(120);
    expect(report.after.runs).toEqual([]);
    expect(report.historical?.runs[0].directions[0].capture_to_first_received_pcm_ms).toBe(12000);
    expect(coldStartReport(null).recorded_at).toBeNull();
    expect(coldStartReport(null).historical).toBeNull();
  });

  it('keeps historical incidents out of the fresh before/after comparison', () => {
    const report = coldStartReport({
      baseline: { runs: [{ passed: true, directions: [direction(400), direction(600)] }] },
      after: { runs: [{ passed: true, directions: [direction(200), direction(300)] }] },
      historical: { runs: [{ passed: true, directions: [direction(12132.83), direction(4669.78)] }] },
    });
    const before = summarizeColdStarts(report.baseline), after = summarizeColdStarts(report.after);
    expect(before.median_ms).toBe(500);
    expect(after.median_ms).toBe(250);
    expect(before.sample_count).toBe(2);
    expect(after.sample_count).toBe(2);
    expect(coldStartReduction(before.median_ms, after.median_ms)).toBe(50);
    expect(report.historical?.runs).toHaveLength(1);
  });
});
