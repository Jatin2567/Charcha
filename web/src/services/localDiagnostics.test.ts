import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ProbeSnapshot } from './audioProbe';
import { fetchLocalDiagnostics, localDiagnosticsReport, screeningSummary } from './localDiagnostics';
import type { RoomScreeningSample, RoomScreeningSnapshot } from './localDiagnostics';

const sample = (patch: Partial<RoomScreeningSample> = {}): RoomScreeningSample => ({
  speaker_id: 'private-speaker', verdict: 'unknown', score: null, compute_ms: 15,
  audio_window_ms: 4037.5, queue_ms: 1, hold_ms: 0, status: 'assessed',
  action: 'observed', mode: 'monitor', created_at: '2026-10-27', reasons: [], ...patch,
});
afterEach(() => vi.unstubAllGlobals());

describe('room local diagnostics', () => {
  it('authenticates bounded room GETs and propagates abort without launching a probe', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    const abort = new AbortController();
    await fetchLocalDiagnostics('room/x', 'private-token', 'screening', abort.signal);
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/rooms/room%2Fx/screening', { signal: abort.signal, headers: { Authorization: 'Bearer private-token' } });
    fetch.mockResolvedValue(new Response('', { status: 401 }));
    await expect(fetchLocalDiagnostics('room', 'private-token', 'audio-probes', abort.signal)).rejects.toThrow('membership expired');
  });
  it('keeps unknown/errors visible and excludes invalid/error compute from percentiles', () => {
    const rows = [sample(), sample({ verdict: 'suspicious', score: .9, compute_ms: 30 }), sample({ status: 'overload', compute_ms: null, hold_ms: null }), sample({ compute_ms: Number.NaN, hold_ms: null })];
    expect(screeningSummary(rows)).toEqual({ count: 4, assessed: 3, flagged: 1, unknown: 3, failed: 1, compute_p50_ms: 15, compute_p95_ms: 30, hold_p50_ms: 0 });
    expect(screeningSummary([]).compute_p50_ms).toBeNull();
  });
  it('exports independent timing boundaries and no room/speaker/probe identities or injected secrets', () => {
    const screening: RoomScreeningSnapshot = {
      mode: 'monitor', experimental: true,
      model: { id: 'aasist', kind: 'onnx_classifier', ready: true, revision: 'rev', sha256: 'hash', license: 'MIT', validated_on_indian_meeting_audio: false },
      latest: { 'private-speaker': sample() }, samples: [sample()],
    };
    const probes: ProbeSnapshot = {
      room_code: 'private-room', generated_at: '2026-10-27',
      measurement: { boundary: 'request_to_decoded_probe_audio', clock: 'single_browser_monotonic', detection: 'dedicated_probe_track_energy', client_reported: true, physical_speaker_output_measured: false, translation_end_to_end_measured: false, includes: [], excludes: [], polling_note: 'test', retention_limit: 100 },
      summary: { sample_count: 1, detected_count: 1, failed_count: 0, cancelled_count: 0, p50_ms: 300, p95_ms: 300 },
      samples: [{ probe_id: 'private-probe', listener_id: 'private-listener', measurement: 'request_to_decoded_probe_audio', status: 'detected', elapsed_ms: 300, poll_interval_ms: 100, server_start_to_report_ms: 315, created_at: '2026-10-27' }],
    };
    const output = localDiagnosticsReport({ ...probes, token: 'private-token' } as ProbeSnapshot, { ...screening, filepath: 'private-path' } as RoomScreeningSnapshot);
    expect(JSON.stringify(output)).not.toContain('private-');
    expect(output.probes?.measurement.translation_end_to_end_measured).toBe(false);
    expect(output.screening?.model.validated_on_indian_meeting_audio).toBe(false);
    expect(output.screening?.samples[0].hold_ms).toBe(0);
  });
});
