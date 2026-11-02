import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import storedEvidence from '../data/speechEndLatencyResults.json';
import { speechEndLatencyReport, summarizeSpeechEnd } from './speechEndLatencyEvidence';
import { SpeechEndLatencyEvidence } from '../components/SpeechEndLatencyEvidence';

const fixture = () => ({
  schema_version: 1,
  record_type: 'speech_end_latency_evidence',
  recorded_on: '2026-10-30',
  evidence_kind: 'synthetic_local_rtc',
  clock: 'single_process_monotonic',
  boundary: 'source_end_to_first_decoded_rtc',
  source_end_reference: 'last_voiced_source_frame_playout',
  physical_playback_measured: false,
  provider_calls: 0,
  screening_mode: 'off',
  voice_cloning: false,
  target_ms: 2000,
  acceptance: 'not_verified',
  samples: [
    {
      trial_id: 'trial-1',
      condition: 'first_route',
      source_language: 'hi',
      target_language: 'ta',
      status: 'complete',
      source_end_to_decoded_ms: -200,
      source_end_to_render_estimate_ms: null,
      source_end_to_physical_playback_ms: null,
    },
    {
      trial_id: 'trial-2',
      condition: 'warm_route',
      source_language: 'hi',
      target_language: 'ta',
      status: 'complete',
      source_end_to_decoded_ms: 80,
      source_end_to_render_estimate_ms: null,
      source_end_to_physical_playback_ms: null,
    },
    {
      trial_id: 'trial-3',
      condition: 'warm_route',
      source_language: 'hi',
      target_language: 'ta',
      status: 'timeout',
      source_end_to_decoded_ms: null,
      source_end_to_render_estimate_ms: null,
      source_end_to_physical_playback_ms: null,
    },
  ],
  summary: { attempted: 3, completed: 2, failed: 1, p50_decoded_ms: -200, p95_decoded_ms: 80 },
  limitations: ['Synthetic local peers with provider doubles. Physical playback is unmeasured.'],
  source_report_sha256: '1'.repeat(64),
});

describe('speech-end timing evidence boundaries', () => {
  it('loads the saved eleven-trial fixture without promoting its ten warm trials to a physical pass', () => {
    const report = speechEndLatencyReport()!;
    expect(report).not.toBeNull();
    expect(report.summary).toEqual({
      attempted: 11,
      completed: 11,
      failed: 0,
      p50_decoded_ms: 927.99,
      p95_decoded_ms: 1042.113,
    });
    const warm = summarizeSpeechEnd(report.samples.filter((row) => row.condition === 'warm_route'));
    expect(warm).toEqual({
      attempted: 10,
      completed: 10,
      failed: 0,
      p50_decoded_ms: 926.287,
      p95_decoded_ms: 956.797,
    });
    expect(report.acceptance).toBe('not_verified');
    expect(report.physical_playback_measured).toBe(false);
    expect(
      report.samples.every(
        (row) =>
          row.source_end_to_render_estimate_ms === null &&
          row.source_end_to_physical_playback_ms === null,
      ),
    ).toBe(true);
  });
  it('validates a real imported fixture when present without fabricating absent data', () => {
    const report = speechEndLatencyReport();
    if (storedEvidence === null) expect(report).toBeNull();
    else expect(report).not.toBeNull();
    expect(speechEndLatencyReport(null)).toBeNull();
    const html = renderToStaticMarkup(createElement(SpeechEndLatencyEvidence, { evidence: null }));
    expect(html).toContain('Not verified');
    expect(html).toContain('N/A');
    expect(html).not.toContain('0 ms');
    expect(html).toContain('Download capture guide');
  });

  it('preserves negative streaming onset and descriptive nearest-rank percentiles', () => {
    const report = speechEndLatencyReport(fixture())!;
    expect(report).not.toBeNull();
    expect(report.samples[0].source_end_to_decoded_ms).toBe(-200);
    expect(report.summary.p50_decoded_ms).toBe(-200);
    const warm = summarizeSpeechEnd(report.samples.filter((row) => row.condition === 'warm_route'));
    expect(warm).toEqual({
      attempted: 2,
      completed: 1,
      failed: 1,
      p50_decoded_ms: 80,
      p95_decoded_ms: 80,
    });
    expect(summarizeSpeechEnd([]).p50_decoded_ms).toBeNull();
  });

  it('cannot promote synthetic decoding to render or physical playback acceptance', () => {
    for (const patch of [
      { physical_playback_measured: true },
      { acceptance: 'pass' },
      { provider_calls: 1 },
      { evidence_kind: 'live' },
      { clock: 'two_device_wall_clocks' },
      { voice_cloning: true },
      { screening_mode: 'enforce' },
    ]) {
      expect(speechEndLatencyReport({ ...fixture(), ...patch })).toBeNull();
    }
    const render = fixture();
    Object.assign(render.samples[0], { source_end_to_render_estimate_ms: 100 });
    expect(speechEndLatencyReport(render)).toBeNull();
    const playback = fixture();
    Object.assign(playback.samples[0], { source_end_to_physical_playback_ms: 100 });
    expect(speechEndLatencyReport(playback)).toBeNull();
  });

  it('retains failure and missing values rather than counting them as zero or successful audio', () => {
    const bad = fixture();
    Object.assign(bad.samples[2], { source_end_to_decoded_ms: 0 });
    expect(speechEndLatencyReport(bad)).toBeNull();
    const missing = fixture();
    Object.assign(missing.samples[0], { source_end_to_decoded_ms: null });
    expect(speechEndLatencyReport(missing)).toBeNull();
    const summary = fixture();
    summary.summary.completed = 3;
    expect(speechEndLatencyReport(summary)).toBeNull();
    const duplicate = fixture();
    duplicate.samples[2].trial_id = 'trial-1';
    expect(speechEndLatencyReport(duplicate)).toBeNull();
    const nonfinite = fixture();
    nonfinite.samples[0].source_end_to_decoded_ms = Number.NaN;
    expect(speechEndLatencyReport(nonfinite)).toBeNull();
  });

  it('exports only public local evidence and isolates subsequent exports from edits', () => {
    const input = {
      ...fixture(),
      api_key: 'NEVER-EXPORT',
      room_code: 'PRIVATE-ROOM',
      flow_id: 'PRIVATE-FLOW',
      endpoint: 'https://private.example',
    };
    Object.assign(input.samples[0], { participant_id: 'PRIVATE-PERSON' });
    const report = speechEndLatencyReport(input)!;
    expect(JSON.stringify(report)).not.toMatch(
      /NEVER-EXPORT|PRIVATE-|api_key|room_code|flow_id|participant_id|endpoint/,
    );
    report.samples[0].source_end_to_decoded_ms = 0;
    report.limitations.push('changed export');
    expect(input.samples[0].source_end_to_decoded_ms).toBe(-200);
    expect(input.limitations).toHaveLength(1);
    expect(
      speechEndLatencyReport({ ...fixture(), limitations: ['Bearer PRIVATE-CREDENTIAL'] }),
    ).toBeNull();
  });

  it('clearly presents software decoding, rendering and real playback as distinct boundaries', () => {
    const html = renderToStaticMarkup(
      createElement(SpeechEndLatencyEvidence, { evidence: speechEndLatencyReport(fixture()) }),
    );
    expect(html).toContain('Under 2 seconds');
    expect(html).toContain('Not verified');
    expect(html).toContain('-200 ms');
    expect(html).toContain('Render estimate');
    expect(html).toContain('Physical listener playback');
    expect(html).toContain('negative offset');
    expect(html).toContain('not clamped to zero');
    expect(html).toContain('one continuous recording clock');
    expect(html).toContain('phone may hear');
    expect(html).toContain('separate JSON record');
    expect(html).toContain('No microphone, camera, tone or provider flow starts');
    expect(html).not.toContain('Goal achieved');
  });
});
