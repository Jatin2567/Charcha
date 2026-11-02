import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import storedEvidence from '../data/tamilHindiFollowupResults.json';
import originalEvidence from '../data/hindiTamilProviderResults.json';
import { tamilHindiFollowupReport } from './tamilHindiFollowupEvidence';
import { TamilHindiFollowupEvidence } from '../components/TamilHindiFollowupEvidence';
import { PROVIDER_CHAIN_COMPLETE } from './hindiTamilProviderEvidence';
import { SavedSpeechTests } from '../components/SavedSpeechTests';

// Deliberately fabricated protocol fixture; never used as production evidence.
const fixture = () => ({
  schema_version: 1,
  record_type: 'controlled_tamil_hindi_followup_evidence',
  recorded_on: '2026-10-30',
  source_report_sha256: '1'.repeat(64),
  plan_sha256: '2'.repeat(64),
  input_sha256: '0c3b3c5a5e78fa824bc633cf21c12fac74f88cde0f708b98f46924dc9b987c39',
  source_audio_seconds: 3.2,
  source_provenance: 'existing_standard_voice_clip',
  source_language: 'ta',
  target_language: 'hi',
  translation_model: 'gnani/gnani-evon-v3.3-30B-A3B',
  prompt_version: 'evon-explicit-target-v2',
  voice_mode: 'standard',
  status: PROVIDER_CHAIN_COMPLETE,
  error_stage: null,
  error_class: null,
  stt: { requested_model: 'prisma-v3.0', provider_model: null },
  timings: {
    stt_final_ms: 100,
    mt_complete_ms: 50,
    target_tts_first_pcm_ms: 30,
    target_tts_complete_ms: 60,
    stt_start_to_target_first_pcm_ms: 180,
    stt_start_to_target_complete_ms: 210,
  },
  used: {
    stt_seconds: 6,
    stt_connections: 1,
    mt_requests: 1,
    mt_characters: 20,
    tts_requests: 1,
    tts_characters: 100,
    voice_enrollments: 0,
  },
  caps: {
    stt_seconds: 25,
    stt_connections: 1,
    mt_requests: 1,
    mt_characters: 500,
    tts_requests: 1,
    tts_characters: 300,
    voice_enrollments: 0,
  },
  wall_seconds: 1.23,
  cleanup_complete: true,
  flow_closed: true,
  meaning_review: 'pending',
  rtc_tested: false,
  physical_microphone_tested: false,
  listener_latency_ms: null,
  voice_cloning: false,
  screening_mode: 'off',
  automatic_retries: 0,
  source_tts_requests: 0,
  cost_reference: {
    currency: 'INR',
    stt_per_hour: 27,
    tts_per_10000_characters: 27,
    local_usage_reference_inr: 0.315,
    approved_maximum_reference_inr: 0.9975,
    actual_provider_charge_inr: null,
    actual_modal_charge_usd: null,
    programme_credits_used: null,
  },
});

describe('separate controlled Tamil to Hindi follow-up', () => {
  it('presents saved usage as history while preserving the current ledger boundary', () => {
    const html = renderToStaticMarkup(createElement(SavedSpeechTests));
    expect(html).toContain('Saved speech tests');
    expect(html).toContain('separate historical records');
    expect(html).toContain('current local session totals');
    expect(html).toContain('keeps its isolated ledger');
    expect(html).toContain('not inferred here');
    expect(html).toContain('Hindi ↔ Tamil provider-chain check');
  });
  it('hides absent results and requires any real imported data to validate before display', () => {
    expect(tamilHindiFollowupReport(null)).toBeNull();
    expect(
      renderToStaticMarkup(createElement(TamilHindiFollowupEvidence, { evidence: null })),
    ).toBe('');
    const report = tamilHindiFollowupReport();
    if (storedEvidence === null) expect(report).toBeNull();
    else expect(report).not.toBeNull();
  });

  it('shows requested versus unconfirmed STT models and keeps upload/setup inside the boundary', () => {
    const evidence = tamilHindiFollowupReport(fixture())!;
    expect(evidence).not.toBeNull();
    expect(evidence.stt.requested_model).toBe('prisma-v3.0');
    expect(evidence.stt.provider_model).toBeNull();
    const html = renderToStaticMarkup(createElement(TamilHindiFollowupEvidence, { evidence }));
    expect(html).toContain('Requested STT model');
    expect(html).toContain('Provider-confirmed STT model');
    expect(html).toContain('Unknown');
    expect(html).toContain('real-time transmission of the source clip');
    expect(html).toContain('not speech-end delay');
    expect(html).toContain('stream close and cleanup before translation');
    expect(html).toContain('stage values need not add up to the full chain');
    expect(html).toContain('No duration is subtracted');
    expect(html).toContain('original two-direction trial remains unchanged');
    expect(html).toContain('3.2-second standard-voice Tamil clip');
    expect(html).toContain('No source TTS request');
    expect(html).not.toMatch(/<details[^>]*\sopen(?:[\s=>])/);
  });

  it('does not accept expanded scope, a changed WAV/model/prompt or invented model confirmation', () => {
    for (const patch of [
      { rtc_tested: true },
      { voice_cloning: true },
      { source_tts_requests: 1 },
      { automatic_retries: 1 },
      { source_audio_seconds: 4 },
      { input_sha256: '3'.repeat(64) },
      { translation_model: 'other' },
      { prompt_version: 'other' },
      { meaning_review: 'approved' },
      { listener_latency_ms: 100 },
      { error_class: 'RAW PRIVATE ERROR' },
    ]) {
      expect(tamilHindiFollowupReport({ ...fixture(), ...patch })).toBeNull();
    }
    expect(
      tamilHindiFollowupReport({
        ...fixture(),
        stt: { requested_model: 'prisma-v3.0', provider_model: 'prisma-v3.0' },
      }),
    ).toBeNull();
    const caps = fixture();
    caps.caps.stt_seconds = 26;
    expect(tamilHindiFollowupReport(caps)).toBeNull();
    const used = fixture();
    used.used.mt_requests = 2;
    expect(tamilHindiFollowupReport(used)).toBeNull();
  });

  it('keeps safe timeout classification, failed stages and unknown metrics visible', () => {
    const input = fixture();
    Object.assign(input, {
      status: 'stopped_no_retry',
      error_stage: 'stt',
      error_class: 'timeout',
    });
    Object.assign(input.used, {
      stt_seconds: 20,
      mt_requests: 0,
      mt_characters: 0,
      tts_requests: 0,
      tts_characters: 0,
    });
    Object.assign(input.cost_reference, { local_usage_reference_inr: 0.15 });
    Object.keys(input.timings).forEach((key) => Object.assign(input.timings, { [key]: null }));
    const evidence = tamilHindiFollowupReport(input)!;
    expect(evidence).not.toBeNull();
    const html = renderToStaticMarkup(createElement(TamilHindiFollowupEvidence, { evidence }));
    expect(html).toContain('Timeout at stt');
    expect(html).toContain('N/A');
    expect(html).toContain('Stopped · no retry');
    expect(html).toContain('₹0.1500');
  });

  it('exports only public fields and never changes the original partial trial', () => {
    const original = JSON.stringify(originalEvidence);
    const input = {
      ...fixture(),
      endpoint: 'https://private.example',
      flow_id: 'private',
      api_key: 'NEVER-EXPORT',
      transcript: 'PRIVATE',
      account_balance: 1000,
    };
    Object.assign(input.timings, { private_field: 'NEVER-EXPORT' });
    const evidence = tamilHindiFollowupReport(input)!;
    const serialized = JSON.stringify(evidence);
    expect(serialized).not.toMatch(
      /endpoint|flow_id|api_key|NEVER-EXPORT|PRIVATE|account_balance|p50|p95/,
    );
    expect(evidence.cost_reference.actual_provider_charge_inr).toBeNull();
    evidence.used!.stt_seconds = 0;
    expect(input.used.stt_seconds).toBe(6);
    expect(JSON.stringify(originalEvidence)).toBe(original);
  });

  it('cannot turn a missing stage, open grant or inconsistent reference into completion', () => {
    const missing = fixture();
    Object.assign(missing.timings, { stt_final_ms: null });
    expect(tamilHindiFollowupReport(missing)).toBeNull();
    expect(tamilHindiFollowupReport({ ...fixture(), flow_closed: false })).toBeNull();
    const price = fixture();
    price.cost_reference.local_usage_reference_inr = 0;
    expect(tamilHindiFollowupReport(price)).toBeNull();
    const order = fixture();
    order.timings.target_tts_first_pcm_ms = 70;
    expect(tamilHindiFollowupReport(order)).toBeNull();
  });
});
