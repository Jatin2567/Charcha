/** No network calls here. The caller explicitly starts one server tone probe.
 * One browser monotonic clock measures request -> decoded dedicated-track energy.
 * This cannot measure translation latency or physical speaker audibility.
 */
export const PROBE_MEASUREMENT = 'request_to_decoded_probe_audio' as const;
export const PROBE_TIMEOUT_MS = 30_000;
const probeIdPattern = /^[A-Za-z0-9_-]{16,64}$/;

export interface ProbeChallenge {
  probe_id: string;
  listener_id: string;
  track_name: string;
  measurement: typeof PROBE_MEASUREMENT;
  expires_in_ms: number;
}

export interface ProbeReport {
  probe_id: string;
  status: 'detected' | 'timeout' | 'cancelled';
  elapsed_ms: number | null;
  poll_interval_ms: number;
  output_enabled: boolean;
}

export interface ProbeSample {
  probe_id: string;
  listener_id: string;
  measurement: typeof PROBE_MEASUREMENT;
  status: ProbeReport['status'] | 'expired' | 'delivery_error';
  elapsed_ms: number | null;
  poll_interval_ms: number | null;
  server_start_to_report_ms: number | null;
  created_at: string;
}

export interface ProbeSnapshot {
  room_code: string;
  generated_at: string;
  measurement: {
    boundary: typeof PROBE_MEASUREMENT;
    clock: 'single_browser_monotonic';
    detection: 'dedicated_probe_track_energy';
    client_reported: true;
    physical_speaker_output_measured: false;
    translation_end_to_end_measured: false;
    includes: string[];
    excludes: string[];
    polling_note: string;
    retention_limit: number;
  };
  summary: {
    sample_count: number;
    detected_count: number;
    failed_count: number;
    cancelled_count: number;
    p50_ms: number | null;
    p95_ms: number | null;
  };
  samples: ProbeSample[];
}

export function isProbeChallenge(value: unknown, listenerId: string): value is ProbeChallenge {
  if (!value || typeof value !== 'object') return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.probe_id === 'string' && probeIdPattern.test(item.probe_id) &&
    item.listener_id === listenerId &&
    item.track_name === `probe:${item.probe_id}:${listenerId}` &&
    item.measurement === PROBE_MEASUREMENT &&
    typeof item.expires_in_ms === 'number' && Number.isFinite(item.expires_in_ms) &&
    item.expires_in_ms > 0 && item.expires_in_ms <= PROBE_TIMEOUT_MS
  );
}

export function probeTrackForListener(trackName: string, listenerId: string): boolean {
  const parts = trackName.split(':');
  return parts.length === 3 && parts[0] === 'probe' &&
    probeIdPattern.test(parts[1]) && parts[2] === listenerId;
}

export class ProbeSignalTracker {
  private startedAt: number | null = null;
  private completed = false;
  private consecutiveSignal = 0;
  private lastObservationAt: number | null = null;

  constructor(
    readonly challenge: ProbeChallenge,
    private readonly clock: () => number = () => performance.now(),
    readonly pollIntervalMs = 100,
  ) {
    if (!isProbeChallenge(challenge, challenge.listener_id)) throw new Error('Invalid audio probe');
    if (!Number.isFinite(pollIntervalMs) || pollIntervalMs < 10 || pollIntervalMs > 1000)
      throw new Error('Invalid audio probe sampling interval');
  }

  /** Call immediately before POSTing start; never use Date.now or server timestamps. */
  start(): void {
    if (this.startedAt !== null || this.completed) throw new Error('Audio probe already started');
    const at = this.clock();
    if (!Number.isFinite(at) || at < 0) throw new Error('Invalid monotonic clock');
    this.startedAt = at;
  }

  /** Observe only the challenge's dedicated received tone track, with playback enabled. */
  observe(trackName: string, level: number, outputEnabled: boolean): ProbeReport | null {
    if (this.startedAt === null || this.completed || trackName !== this.challenge.track_name)
      return null;
    const at = this.clock();
    if (!Number.isFinite(at) || at < this.startedAt ||
        (this.lastObservationAt !== null && at < this.lastObservationAt))
      return this.finish('cancelled', null, outputEnabled);
    if (at - this.startedAt > PROBE_TIMEOUT_MS)
      return this.finish('timeout', null, outputEnabled);
    // A duplicated callback in one polling tick is not a second signal observation.
    if (this.lastObservationAt !== null && at - this.lastObservationAt < this.pollIntervalMs / 2)
      return null;
    this.lastObservationAt = at;
    if (!outputEnabled || !Number.isFinite(level) || level < 0.008 || level > 1) {
      this.consecutiveSignal = 0;
      return null;
    }
    this.consecutiveSignal++;
    if (this.consecutiveSignal < 2 || at === this.startedAt) return null;
    return this.finish('detected', Math.round((at - this.startedAt) * 100) / 100, true);
  }

  timeout(): ProbeReport | null {
    if (this.startedAt === null || this.completed) return null;
    return this.finish('timeout', null, false);
  }

  cancel(): ProbeReport | null {
    if (this.startedAt === null || this.completed) return null;
    return this.finish('cancelled', null, false);
  }

  private finish(status: ProbeReport['status'], elapsedMs: number | null, outputEnabled: boolean): ProbeReport {
    this.completed = true;
    return {
      probe_id: this.challenge.probe_id,
      status,
      elapsed_ms: elapsedMs,
      poll_interval_ms: this.pollIntervalMs,
      output_enabled: outputEnabled,
    };
  }
}
