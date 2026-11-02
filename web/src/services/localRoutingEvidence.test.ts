import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { localRoutingReport } from './localRoutingEvidence';
import { LocalRoutingEvidence } from '../components/LocalRoutingEvidence';

describe('saved local first-audio routing evidence', () => {
  it('accounts for all twenty language directions and the extra recipient routes', () => {
    const report = localRoutingReport();
    expect(report.languages).toEqual(['hi', 'ta', 'bn', 'te', 'mr']);
    expect(report.observations).toHaveLength(25);
    const translated = report.observations.filter((row) => row.kind === 'synthetic_translation');
    const unique = new Set(translated.map((row) => `${row.source_language}:${row.target_language}`));
    expect(translated).toHaveLength(24);
    expect(unique.size).toBe(report.translation_branches);
    expect(report.translation_branches).toBe(20);
    for (const source of report.languages) {
      expect(report.observations.filter((row) => row.source_language === source)).toHaveLength(5);
      for (const target of report.languages.filter((language) => language !== source)) {
        expect(unique.has(`${source}:${target}`)).toBe(true);
      }
    }
    const forwarded = report.observations.filter((row) => row.kind === 'same_language_forwarding');
    expect(forwarded).toHaveLength(1);
    expect(forwarded[0].source_language).toBe('ta');
    expect(forwarded[0].target_language).toBe('ta');
  });

  it('preserves first-audio boundaries, incomplete acceptance and the shutdown warning', () => {
    const report = localRoutingReport();
    expect(report.scope).toBe('first_nonzero_decoded_pcm_per_route');
    expect(report.wall_seconds).toBe(40.738);
    expect(report.synthetic_camera_receivers).toBe(5);
    expect(report.provider_requests).toBe(0);
    expect(report.continuous_playback_verified).toBe(false);
    expect(report.simultaneous_speech_verified).toBe(false);
    expect(report.live_provider_capacity_verified).toBe(false);
    expect(report.physical_device_acceptance_verified).toBe(false);
    expect(report.listener_playback_latency_ms).toBeNull();
    expect(report.prior_stress_failures_preserved).toBe(true);
    expect(report.shutdown_warning).toContain('already closed connection');
    expect(report.source_report_sha256).toBe('342ae5b17b545ae4ebb9dd741188a4ff5c19ce90113cf2c04e6326de9f57002b');
    expect(report.observations.every((row) => Number.isFinite(row.capture_to_first_received_pcm_ms) && row.capture_to_first_received_pcm_ms > 0)).toBe(true);
  });

  it('exports an isolated public fixture with no room state or private configuration', () => {
    const report = localRoutingReport();
    const serialized = JSON.stringify(report);
    expect(serialized).not.toMatch(/api_key|modal_secret|session_token|https?:\/\/|participant_id|room_code|source_peer|listener_peer/i);
    expect(Object.keys(report).some((key) => /p50|p95|median/i.test(key))).toBe(false);
    report.observations[0].capture_to_first_received_pcm_ms = 0;
    report.languages.pop();
    expect(localRoutingReport().observations[0].capture_to_first_received_pcm_ms).toBeGreaterThan(0);
    expect(localRoutingReport().languages).toHaveLength(5);
  });

  it('keeps the UI collapsed and labels the evidence separately from real latency', () => {
    const html = renderToStaticMarkup(createElement(LocalRoutingEvidence));
    expect(html).toContain('Local routing check');
    expect(html).toContain('Synthetic · first-audio only');
    expect(html).toContain('no p50 or p95 is inferred');
    expect(html).toContain('Their measurements stay N/A until tested');
    expect(html).toContain('Shutdown warning retained');
    expect(html).toContain('Export result');
    expect(html).not.toMatch(/<details[^>]*\sopen(?:[\s=>])/);
  });
});
