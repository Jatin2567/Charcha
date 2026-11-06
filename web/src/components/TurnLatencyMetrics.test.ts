import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { TurnLatencyMetrics } from './TurnLatencyMetrics';
import { ReportPersistence } from './ReportPersistence';
import type { TurnLatencyReport } from '../types/performance';

const report: TurnLatencyReport = {
  measurement: 'server_ingress_energy_end_to_browser_decoded_onset_estimate', physical_playback_measured: false,
  samples: [{ marker_id: 'm', utterance_id: 'u', listener_id: 'private-id', source_language: 'hi', target_language: 'ta',
    status: 'detected', source_end_status: 'energy_estimate', latency_ms: 1234, uncertainty_ms: 140,
    source_end_to_first_pcm_ms: 900, physical_playback_measured: false, client_reported: true, created_at: '' }],
};
describe('truthful automatic latency and persistence UI', () => {
  it('shows measured estimates with uncertainty and the actual boundaries', () => {
    const html = renderToStaticMarkup(createElement(TurnLatencyMetrics, { report }));
    expect(html).toContain('1,234 ms'); expect(html).toContain('140 ms');
    expect(html).toContain('physical speaker output are not measured');
    expect(html).not.toContain('private-id');
  });
  it('excludes unknown/blocked readings instead of treating them as zero or successful playback', () => {
    const html = renderToStaticMarkup(createElement(TurnLatencyMetrics, { report: { ...report,
      samples: [{ ...report.samples[0], status: 'source_unavailable', latency_ms: null, uncertainty_ms: null }] } }));
    expect(html).toContain('N/A'); expect(html).not.toContain('0 ms');
    expect(html).toContain('Source speech end could not be matched confidently');
    expect(html).toContain('1 attempts had no trustworthy interval');
  });
  it('filters languages without carrying an earlier pair into the percentiles', () => {
    const html = renderToStaticMarkup(createElement(TurnLatencyMetrics, { report, direction: 'en:hi' }));
    expect(html).not.toContain('1,234'); expect(html).toContain('No listener observations yet');
  });
  it('distinguishes committed reports from pending memory and saving failures', () => {
    const html = renderToStaticMarkup(createElement(ReportPersistence, { status: {
      state: 'retrying', pending: 1, last_saved_at: null, error: 'safe message',
    } }));
    expect(html).toContain('could be lost if the server stops');
    expect(html).not.toContain('Report saved.'); expect(html).not.toContain('1970');
  });
});
