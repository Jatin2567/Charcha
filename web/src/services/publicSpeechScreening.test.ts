import { describe, expect, it } from 'vitest';
import saved from '../data/publicHumanScreeningResults.json';
import { PUBLIC_SPEECH_LANGUAGES, publicHumanScreeningReport } from './publicSpeechScreening';

const pending = {
  ...saved,
  status: 'not_run',
  measured_at: null,
  model: { id: 'SpeechAntiSpoofingBenchmarks/AASIST', sha256: null },
  baseline_by_language: [],
  prefix_summary: [],
};
const completed = () => ({
  ...pending,
  status: 'complete',
  measured_at: '2026-10-29T12:00:00Z',
  model: { id: 'SpeechAntiSpoofingBenchmarks/AASIST', sha256: '1'.repeat(64) },
  baseline_by_language: PUBLIC_SPEECH_LANGUAGES.map((language) => ({
    language,
    recordings: 10,
    allow: 3,
    suspicious: 4,
    unknown: 3,
    errors: 0,
    unattempted: 0,
    compute_p50_ms: 200,
    compute_p95_ms: 280,
  })),
  prefix_summary: [500, 1000, 2000, 3000].map((observed_audio_ms) => ({
    observed_audio_ms,
    recordings: 50,
    suspicious: 15,
    unknown: 25,
    errors: 0,
    unattempted: 0,
    verdict_changes_from_full: 20,
    paired_comparisons: 50,
  })),
});

describe('saved public human speech screening evidence', () => {
  it('validates the committed saved record through the same export contract', () => {
    expect(publicHumanScreeningReport(saved)).not.toBeNull();
  });

  it('keeps a pending record unmeasured instead of creating zero-error results', () => {
    const report = publicHumanScreeningReport(pending)!;
    expect(report.status).toBe('not_run');
    expect(report.measured_at).toBeNull();
    expect(report.baseline_by_language).toEqual([]);
    expect(report.prefix_summary).toEqual([]);
    expect(report.accuracy).toBeNull();
    expect(report.ai_detection_rate).toBeNull();
    expect(report.independent_speaker_count).toBeNull();
  });

  it('preserves all false alarms and unknowns without treating them as correct human classifications', () => {
    const report = publicHumanScreeningReport(completed())!;
    expect(report.status).toBe('complete');
    expect(report.baseline_by_language).toHaveLength(5);
    expect(report.baseline_by_language[0]).toMatchObject({
      allow: 3,
      suspicious: 4,
      unknown: 3,
      recordings: 10,
    });
    expect(report.prefix_summary[0]).toMatchObject({
      observed_audio_ms: 500,
      suspicious: 15,
      unknown: 25,
      paired_comparisons: 50,
    });
    expect(report.baseline_ms).toBe(4037.5);
    expect(report.live_window_changed).toBe(false);
    expect(report.voice_cloning).toBe(false);
  });

  it('exports only the public contract without private runtime fields', () => {
    const input = completed();
    const report = publicHumanScreeningReport({
      ...input,
      private_path: 'private-root',
      session_token: 'private-secret',
      source: { ...input.source, local_audio: 'private-audio' },
      model: { ...input.model, model_path: 'private-model' },
      baseline_by_language: input.baseline_by_language.map((row) => ({
        ...row,
        transcript: 'private-transcript',
        speaker_id: 'private-person',
      })),
      prefix_summary: input.prefix_summary.map((row) => ({ ...row, waveform: 'private-samples' })),
    });
    expect(report).not.toBeNull();
    expect(JSON.stringify(report)).not.toContain('private-');
    expect(report?.baseline_by_language[0]).not.toBe(input.baseline_by_language[0]);
    expect(report?.model).not.toBe(input.model);
  });

  it('rejects inconsistent counts, duplicate languages, malformed numbers and impossible pairings', () => {
    const mutations = [
      (input: ReturnType<typeof completed>) => {
        input.baseline_by_language[0].unknown = 11;
      },
      (input: ReturnType<typeof completed>) => {
        input.baseline_by_language[0].allow = -1;
      },
      (input: ReturnType<typeof completed>) => {
        input.baseline_by_language[0].compute_p50_ms = NaN;
      },
      (input: ReturnType<typeof completed>) => {
        input.baseline_by_language[0].compute_p95_ms = Infinity;
      },
      (input: ReturnType<typeof completed>) => {
        input.baseline_by_language[0].compute_p50_ms = 300;
      },
      (input: ReturnType<typeof completed>) => {
        input.baseline_by_language[1].language = 'hi';
      },
      (input: ReturnType<typeof completed>) => {
        input.prefix_summary[0].recordings = 49;
      },
      (input: ReturnType<typeof completed>) => {
        input.prefix_summary[0].paired_comparisons = 51;
      },
      (input: ReturnType<typeof completed>) => {
        input.prefix_summary[0].verdict_changes_from_full = 51;
      },
      (input: ReturnType<typeof completed>) => {
        input.prefix_summary[1].observed_audio_ms = 500;
      },
    ];
    for (const mutate of mutations) {
      const input = completed();
      mutate(input);
      expect(publicHumanScreeningReport(input)).toBeNull();
    }
    expect(publicHumanScreeningReport(null)).toBeNull();
    expect(publicHumanScreeningReport([])).toBeNull();
    expect(publicHumanScreeningReport({ ...completed(), schema_version: 99 })).toBeNull();
  });

  it('retains failed and unattempted results only under partial status', () => {
    const input = completed();
    input.status = 'partial';
    input.baseline_by_language[0] = {
      ...input.baseline_by_language[0],
      allow: 1,
      errors: 1,
      unattempted: 1,
    };
    input.prefix_summary.forEach((row) => {
      row.paired_comparisons = 48;
    });
    input.prefix_summary[0] = {
      ...input.prefix_summary[0],
      errors: 2,
      unattempted: 2,
      paired_comparisons: 46,
    };
    const report = publicHumanScreeningReport(input)!;
    expect(report.status).toBe('partial');
    expect(report.baseline_by_language[0]).toMatchObject({ errors: 1, unattempted: 1 });
    expect(report.prefix_summary[0]).toMatchObject({
      errors: 2,
      unattempted: 2,
      paired_comparisons: 46,
    });
    expect(publicHumanScreeningReport({ ...input, status: 'complete' })).toBeNull();
    input.prefix_summary[1].paired_comparisons = 49;
    expect(publicHumanScreeningReport(input)).toBeNull();
  });

  it('cannot label human-only evidence as AI detection accuracy or change provenance and live policy', () => {
    for (const change of [
      { accuracy: 1 },
      { ai_detection_rate: 1 },
      { independent_speaker_count: 50 },
      { synthetic_recordings: 50 },
      { voice_cloning: true },
      { provider_calls: 1 },
      { live_window_changed: true },
      { source: { ...pending.source, license: 'unknown' } },
      { source: { ...pending.source, revision: 'main' } },
      { measured_at: 'private-date' },
    ])
      expect(publicHumanScreeningReport({ ...completed(), ...change })).toBeNull();
  });
});
