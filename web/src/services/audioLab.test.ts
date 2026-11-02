import { afterEach, describe, expect, it, vi } from 'vitest';
import { analyzeAudio, audioLabReport, diagnosticWav, getAudioLabStatus, inspectScreeningWav, recordSharedLatency, sharedLatencySummary } from './audioLab';
import type { AudioScreenResult, ScreeningObservation } from '../types/audioLab';

const result = (): AudioScreenResult => ({
  verdict: 'unknown', score: null, experimental: true, score_calibrated: false,
  threshold: null, allow_threshold: null, compute_ms: 12, audio_window_ms: 5000,
  analyzed_ms: 4040, windows_analyzed: 1, partial_window_ms: 960,
  reasons: ['silence'],
  model: { id: 'signal-checks', kind: 'signal_only', revision: null, sha256: null, ready: false, license: null, validated_on_indian_meeting_audio: false },
  diagnostics: { rms_dbfs: -120, peak: 0, clipping_ratio: 0, silence_ratio: 1, zero_crossing_rate: 0, pitch_hz: null, jitter_percent: null, shimmer_percent: null, voiced_frames: 0, variation_method: 'consecutive_voiced_frame_proxy_not_cycle_measurement' },
});
afterEach(() => vi.unstubAllGlobals());

describe('local audio preflight', () => {
  it('creates bounded silence, tone and clipping WAV fixtures without playing or uploading them', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    for (const kind of ['silence', 'tone', 'clipping'] as const) {
      const buffer = diagnosticWav(kind);
      expect(inspectScreeningWav(buffer)).toEqual({ seconds: 5, sample_rate: 16000, channels: 1, bits: 16 });
      const samples = new Int16Array(buffer.slice(44));
      if (kind === 'silence') expect(samples.every((value) => value === 0)).toBe(true);
      else if (kind === 'clipping') expect(samples.every((value) => value === 32767 || value === -32768)).toBe(true);
      else expect(Math.max(...samples)).toBeLessThanOrEqual(5000);
    }
    expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects renamed compressed input, incomplete payloads and incompatible PCM format', () => {
    expect(() => inspectScreeningWav(new ArrayBuffer(10))).toThrow('too short');
    const buffer = diagnosticWav('tone');
    new DataView(buffer).setUint16(22, 2, true);
    expect(() => inspectScreeningWav(buffer)).toThrow('mono');
    expect(() => inspectScreeningWav(diagnosticWav('tone').slice(0, 100))).toThrow('incomplete');
    expect(() => inspectScreeningWav(new ArrayBuffer(44))).toThrow('uncompressed');
  });
  it('rejects malformed chunk lengths and oversized files before allocating decoded audio', () => {
    const malformed = diagnosticWav('tone');
    new DataView(malformed).setUint32(40, 0xfffffff0, true);
    expect(() => inspectScreeningWav(malformed)).toThrow('incomplete audio chunk');
    expect(() => inspectScreeningWav(new ArrayBuffer(1_024_001))).toThrow('smaller than');
  });
  it('rejects data before fmt, truncated chunk headers and inconsistent sample alignment', () => {
    const wrongOrder = diagnosticWav('tone');
    const bytes = new Uint8Array(wrongOrder);
    bytes.set(new TextEncoder().encode('data'), 12);
    expect(() => inspectScreeningWav(wrongOrder)).toThrow('before its audio data');
    const odd = diagnosticWav('tone');
    new DataView(odd).setUint32(40, 159999, true);
    expect(() => inspectScreeningWav(odd)).toThrow('complete PCM');
    const shortHeader = new Uint8Array(diagnosticWav('tone').byteLength + 4);
    shortHeader.set(new Uint8Array(diagnosticWav('tone')));
    new DataView(shortHeader.buffer).setUint32(4, shortHeader.byteLength - 8, true);
    expect(() => inspectScreeningWav(shortHeader.buffer)).toThrow('incomplete chunk header');
  });
  it('does not contact a server until valid audio and processing consent are present', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    const file = new File([diagnosticWav('silence')], 'private-name.wav');
    await expect(analyzeAudio(file, false)).rejects.toThrow('permission');
    await expect(analyzeAudio(new File(['not audio'], 'renamed.wav'), true)).rejects.toThrow('too short');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('posts only to the local analysis endpoint and requires an honest zero-provider response', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ schema_version: 1, provider_calls: 0, persisted: false, result: result() }), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    await expect(analyzeAudio(new File([diagnosticWav('silence')], 'sample.wav'), true)).resolves.toMatchObject({ provider_calls: 0 });
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe('/api/audio-lab/analyze');
    const options = fetch.mock.calls[0][1];
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.get('consent')).toBe('true');
    expect(options.headers).not.toHaveProperty('Authorization');
    fetch.mockResolvedValue(new Response(JSON.stringify({ schema_version: 1, provider_calls: 1, persisted: false, result: result() }), { status: 200 }));
    await expect(analyzeAudio(new File([diagnosticWav('silence')], 'sample.wav'), true)).rejects.toThrow('local-only');
  });
  it('rejects fabricated confident labels without a usable learned score', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ schema_version: 1, provider_calls: 0, persisted: false, result: { ...result(), verdict: 'allow' } }), { status: 200 })));
    await expect(analyzeAudio(new File([diagnosticWav('silence')], 'sample.wav'), true)).rejects.toThrow('local-only');
  });
  it('keeps a missing or nonlocal status unavailable rather than pretending screening is ready', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ enabled: true, provider_calls: 2, persisted: false }), { status: 200 })));
    await expect(getAudioLabStatus()).rejects.toThrow('local-only');
  });
});

describe('shared-recording timing', () => {
  it('records a manual interval with explicit shared timeline and recording provenance', () => {
    const row = recordSharedLatency('4.250', '4.680', 'original_audio', 'recording-1', '30');
    expect(row).toMatchObject({ source_event_ms: 4250, source_event: 'source_marker_start', receiver_start_ms: 4680, delay_ms: 430, boundary: 'manual_shared_recording', recording_duration_ms: 30000, recording_id: 'recording-1' });
    expect(recordSharedLatency('1', '2', 'standard_translation', 'translation-1', '4').source_event).toBe('source_phrase_end');
  });
  it('rejects blanks, nonfinite positions, negative durations and positions outside the recording', () => {
    for (const [start, end] of [['', '1'], ['NaN', '1'], ['1', 'Infinity'], ['2', '1'], ['-1', '2'], ['0', '121']])
      expect(() => recordSharedLatency(start, end, 'original_audio', 'test', '300')).toThrow();
    expect(() => recordSharedLatency('1', '2', 'original_audio', 'test', '1.5')).toThrow('duration');
    expect(() => recordSharedLatency('1', '2', 'original_audio', 'private file.wav', '3')).toThrow('anonymous');
  });
  it('keeps original transport and translation percentiles separate and excludes invalid values', () => {
    const raw = recordSharedLatency('1', '1.1', 'original_audio', 'a', '3');
    const translated = recordSharedLatency('1', '2', 'standard_translation', 'b', '3');
    const invalid = { ...raw, delay_ms: Number.NaN };
    expect(sharedLatencySummary([raw, translated, invalid], 'original_audio')).toEqual({ count: 1, p50_ms: 100, p95_ms: 100 });
    expect(sharedLatencySummary([], 'original_audio')).toEqual({ count: 0, p50_ms: null, p95_ms: null });
  });
});

describe('privacy-safe audio reports', () => {
  it('exports diagnostics with annotation labels, preserves unknowns and omits raw/file/private fields', () => {
    const sample: ScreeningObservation = { id: 'one', observed_at: '2026-10-27', expected_label: 'unlabelled', diagnostic_fixture: 'silence', result: result() };
    const injected = { ...sample, filename: 'private-name.wav', audio: 'private-audio', result: { ...sample.result, transcript: 'private-words', model: { ...sample.result.model, token: 'private-key' }, diagnostics: { ...sample.result.diagnostics, raw: 'private-raw' } } };
    const report = audioLabReport([injected], []);
    expect(report.screening[0]).toMatchObject({ verdict: 'unknown', score: null, diagnostic_fixture: 'silence' });
    expect(JSON.stringify(report)).not.toContain('private-');
    expect(report).not.toHaveProperty('accuracy');
    expect(report.latency_summary.original_audio.p95_ms).toBeNull();
  });
});
