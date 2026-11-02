import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { hindiTamilProviderReport, PROVIDER_CHAIN_COMPLETE } from './hindiTamilProviderEvidence';
import { HindiTamilProviderEvidence } from '../components/HindiTamilProviderEvidence';
import storedEvidence from '../data/hindiTamilProviderResults.json';

// Fabricated protocol-only fixture; never imported by the production entry point.
const fixture = () => ({
  schema_version: 1,
  record_type: 'controlled_hindi_tamil_provider_evidence',
  recorded_on: '2026-10-30',
  source_report_sha256: '1'.repeat(64),
  plan_sha256: '2'.repeat(64),
  source_provenance: 'deliberately_generated_stock_voice_utterances',
  voice_mode: 'standard',
  status: PROVIDER_CHAIN_COMPLETE,
  error_stage: null,
  cases: [
    ['hi-ta-meeting-time', 'hi', 'ta'],
    ['ta-hi-book-colour', 'ta', 'hi'],
  ].map(([case_id, source_language, target_language]) => ({
    case_id,
    source_language,
    target_language,
    status: PROVIDER_CHAIN_COMPLETE,
    meaning_review: 'pending',
    source_preparation: { first_pcm_ms: 10, complete_ms: 20 },
    stt_final_ms: 100,
    mt_complete_ms: 50,
    target_synthesis: { first_pcm_ms: 30, complete_ms: 60 },
    stt_start_to_target_first_pcm_ms: 180,
    stt_start_to_target_complete_ms: 210,
  })),
  used: {
    stt_seconds: 6,
    stt_connections: 2,
    mt_requests: 2,
    mt_characters: 90,
    tts_requests: 4,
    tts_characters: 100,
    voice_enrollments: 0,
  },
  caps: {
    stt_seconds: 30,
    stt_connections: 2,
    mt_requests: 2,
    mt_characters: 1000,
    tts_requests: 4,
    tts_characters: 800,
    voice_enrollments: 0,
  },
  wall_seconds: 1.23,
  wall_target_seconds: 240,
  wall_target_exceeded: false,
  cleanup_complete: true,
  meaning_review: 'pending',
  rtc_tested: false,
  physical_microphone_tested: false,
  listener_latency_ms: null,
  voice_cloning: false,
  screening_mode: 'off',
  automatic_retries: 0,
  cost_reference: {
    currency: 'INR',
    stt_per_hour: 27,
    tts_per_10000_characters: 27,
    local_usage_reference_inr: 0.315,
    approved_maximum_reference_inr: 2.385,
    actual_provider_charge_inr: null,
    actual_modal_charge_usd: null,
    programme_credits_used: null,
  },
});

describe('controlled provider-chain evidence', () => {
  it('validates any imported evidence and exposes the default card only when it exists', () => {
    const report = hindiTamilProviderReport();
    const html = renderToStaticMarkup(createElement(HindiTamilProviderEvidence));
    if (storedEvidence === null) {
      expect(report).toBeNull();
      expect(html).toBe('');
    } else {
      expect(report).not.toBeNull();
      expect(report?.cases).toHaveLength(2);
      expect(html).toContain('Hindi ↔ Tamil provider-chain check');
      expect(html).toContain('Actual Gnani charge');
    }
  });
  it('hides absent evidence and rejects plans, room reports and unsupported acceptance claims', () => {
    expect(hindiTamilProviderReport(null)).toBeNull();
    expect(hindiTamilProviderReport({ record_type: 'hindi_tamil_provider_chain_plan' })).toBeNull();
    expect(
      renderToStaticMarkup(createElement(HindiTamilProviderEvidence, { evidence: null })),
    ).toBe('');
    for (const patch of [
      { rtc_tested: true },
      { physical_microphone_tested: true },
      { voice_cloning: true },
      { screening_mode: 'monitor' },
      { listener_latency_ms: 180 },
      { meaning_review: 'approved' },
    ]) {
      expect(hindiTamilProviderReport({ ...fixture(), ...patch })).toBeNull();
    }
  });

  it('exports only allowed measurements and leaves account/billing/meaning data unknown', () => {
    const input = {
      ...fixture(),
      api_key: 'NEVER-EXPORT',
      account_balance: 5000,
      flow_id: 'private',
      endpoint: 'https://private.example',
      boundary: 'NEVER-EXPORT',
    };
    Object.assign(input.cases[0], { recognized_text: 'PRIVATE TRANSCRIPT', audio: 'private.wav' });
    const report = hindiTamilProviderReport(input)!;
    expect(report).not.toBeNull();
    expect(report.used?.tts_characters).toBe(100);
    expect(report.cost_reference.local_usage_reference_inr).toBe(0.315);
    expect(report.cost_reference.actual_provider_charge_inr).toBeNull();
    expect(report.listener_latency_ms).toBeNull();
    const serialized = JSON.stringify(report);
    expect(serialized).not.toMatch(
      /NEVER-EXPORT|PRIVATE TRANSCRIPT|private\.wav|api_key|account_balance|flow_id|endpoint|p50|p95/,
    );
    report.cases[0].source_preparation!.complete_ms = 0;
    report.used!.tts_characters = 0;
    expect(input.cases[0].source_preparation.complete_ms).toBe(20);
    expect(input.used.tts_characters).toBe(100);
  });

  it('rejects enlarged caps, inconsistent units, missing stages and substituted case identities', () => {
    const caps = fixture();
    caps.caps.tts_characters = 900;
    expect(hindiTamilProviderReport(caps)).toBeNull();
    const units = fixture();
    units.used.tts_characters = 801;
    expect(hindiTamilProviderReport(units)).toBeNull();
    const missing = fixture();
    Object.assign(missing.cases[0], { stt_final_ms: null });
    expect(hindiTamilProviderReport(missing)).toBeNull();
    const wrong = fixture();
    wrong.cases[0].source_language = 'bn';
    expect(hindiTamilProviderReport(wrong)).toBeNull();
    const invalid = fixture();
    invalid.cases[0].mt_complete_ms = Number.NaN;
    expect(hindiTamilProviderReport(invalid)).toBeNull();
    const price = fixture();
    price.cost_reference.local_usage_reference_inr = 0;
    expect(hindiTamilProviderReport(price)).toBeNull();
  });

  it('keeps source preparation apart from chain timings and does not label protocol completion as semantic acceptance', () => {
    const report = hindiTamilProviderReport(fixture())!;
    const html = renderToStaticMarkup(
      createElement(HindiTamilProviderEvidence, { evidence: report }),
    );
    expect(html).toContain('Controlled stock speech · no RTC');
    expect(html).toContain('Source TTS preparation · excluded from chain');
    expect(html).toContain('STT start → first target PCM');
    expect(html).toContain('connection setup and real-time source-audio transmission');
    expect(html).toContain('it is not speech-end delay');
    expect(html).toContain('Bilingual meaning review is pending');
    expect(html).toContain('Unknown');
    expect(html).toContain('STT reserved time');
    expect(html).toContain('₹0.3150');
    expect(html).toContain('cannot establish p50 or p95');
    expect(html).not.toMatch(/<details[^>]*\sopen(?:[\s=>])/);
  });

  it('retains partial failed cases and unknown local usage without filling missing timings', () => {
    const input = fixture();
    Object.assign(input, {
      status: 'stopped_no_retry',
      error_stage: 'source_tts',
      used: null,
      cleanup_complete: false,
    });
    Object.assign(input.cost_reference, { local_usage_reference_inr: null });
    input.cases.forEach((row, index) =>
      Object.assign(row, {
        status: index ? 'unattempted' : 'error',
        source_preparation: null,
        target_synthesis: null,
        stt_final_ms: null,
        mt_complete_ms: null,
        stt_start_to_target_first_pcm_ms: null,
        stt_start_to_target_complete_ms: null,
      }),
    );
    const report = hindiTamilProviderReport(input)!;
    expect(report).not.toBeNull();
    const html = renderToStaticMarkup(
      createElement(HindiTamilProviderEvidence, { evidence: report }),
    );
    expect(html).toContain('Not attempted');
    expect(html).toContain('N/A');
    expect(html).toContain('incomplete; review required');
    expect(html).toContain('Stopped · no retry');
  });
});
