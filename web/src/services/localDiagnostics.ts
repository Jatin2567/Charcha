import { API_BASE } from './api';
import type { ProbeSnapshot } from './audioProbe';
import type { ScreeningModel, ScreeningVerdict } from '../types/audioLab';

export interface RoomScreeningSample {
  speaker_id: string;
  verdict: ScreeningVerdict;
  score: number | null;
  compute_ms: number | null;
  audio_window_ms: number;
  queue_ms: number | null;
  hold_ms: number | null;
  status: 'assessed' | 'overload' | 'error';
  action: 'observed' | 'released' | 'withheld';
  mode: 'off' | 'monitor' | 'enforce';
  created_at: string;
  reasons: string[];
}
export interface RoomScreeningStatus {
  switchable?: boolean;
  mode: 'off' | 'monitor' | 'enforce';
  model: ScreeningModel & { window_ms?: number; reason?: string; threshold?: number; allow_threshold?: number };
}
export interface RoomScreeningSnapshot extends RoomScreeningStatus {
  latest: Record<string, RoomScreeningSample>;
  samples: RoomScreeningSample[];
  experimental: true;
}

export async function fetchLocalDiagnostics<T>(code: string, token: string, resource: 'screening' | 'audio-probes', signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/rooms/${encodeURIComponent(code)}/${resource}`, { signal, headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new Error(`Local diagnostics unavailable (${response.status}). Rejoin the room if your membership expired.`);
  return response.json() as Promise<T>;
}

const finite = (value: number | null) => value !== null && Number.isFinite(value) && value >= 0 ? value : null;
const percentile = (values: number[], p: number) => values.length ? [...values].sort((a, b) => a - b)[Math.max(0, Math.ceil(values.length * p) - 1)] : null;
export function screeningSummary(samples: RoomScreeningSample[]) {
  const assessed = samples.filter((row) => row.status === 'assessed');
  const values = (key: 'compute_ms' | 'hold_ms') => assessed.map((row) => finite(row[key])).filter((value): value is number => value !== null);
  return {
    count: samples.length, assessed: assessed.length,
    flagged: samples.filter((row) => row.verdict === 'suspicious').length,
    unknown: samples.filter((row) => row.verdict === 'unknown').length,
    failed: samples.filter((row) => row.status !== 'assessed').length,
    compute_p50_ms: percentile(values('compute_ms'), .5),
    compute_p95_ms: percentile(values('compute_ms'), .95),
    hold_p50_ms: percentile(values('hold_ms'), .5),
  };
}

export function localDiagnosticsReport(probes: ProbeSnapshot | null, screening: RoomScreeningSnapshot | null) {
  return {
    schema_version: 1, generated_at: new Date().toISOString(),
    boundary_note: 'Probe timing is client-reported request-to-decoded dedicated-track signal. It does not measure physical speaker output or translation end-to-end. Screening remains experimental.',
    probes: probes ? {
      measurement: {
        boundary: probes.measurement.boundary, clock: probes.measurement.clock,
        client_reported: true, physical_speaker_output_measured: false,
        translation_end_to_end_measured: false,
      },
      summary: {
        sample_count: probes.summary.sample_count, detected_count: probes.summary.detected_count,
        failed_count: probes.summary.failed_count, cancelled_count: probes.summary.cancelled_count,
        p50_ms: probes.summary.p50_ms, p95_ms: probes.summary.p95_ms,
      },
      samples: probes.samples.map((sample) => ({
        measurement: sample.measurement, status: sample.status,
        elapsed_ms: sample.elapsed_ms, poll_interval_ms: sample.poll_interval_ms,
        server_start_to_report_ms: sample.server_start_to_report_ms, created_at: sample.created_at,
      })),
    } : null,
    screening: screening ? {
      mode: screening.mode, experimental: true,
      hold_boundary: 'estimated_window_duration_plus_screening_elapsed_not_receiver_playback',
      model: {
        id: screening.model.id, kind: screening.model.kind, ready: screening.model.ready,
        revision: screening.model.revision, sha256: screening.model.sha256,
        license: screening.model.license, validated_on_indian_meeting_audio: false,
      },
      summary: screeningSummary(screening.samples),
      samples: screening.samples.map((sample) => ({
        verdict: sample.verdict, score: sample.score, compute_ms: sample.compute_ms,
        audio_window_ms: sample.audio_window_ms, queue_ms: sample.queue_ms,
        hold_ms: sample.hold_ms, status: sample.status, action: sample.action,
        mode: sample.mode, created_at: sample.created_at,
      })),
    } : null,
  };
}
