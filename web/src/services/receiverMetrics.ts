import { PROBE_MEASUREMENT } from './audioProbe';

const statuses = ['detected', 'timeout', 'cancelled', 'expired', 'delivery_error'] as const;
type ReceiverStatus = (typeof statuses)[number];
const object = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
const time = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0;

export interface ReceiverProbeReport {
  schema_version: 1;
  record_type: 'receiver_audio_probe_metrics';
  generated_at: string;
  measurement: {
    boundary: typeof PROBE_MEASUREMENT;
    clock: 'single_browser_monotonic';
    client_reported: true;
    physical_speaker_output_measured: false;
    translation_end_to_end_measured: false;
  };
  summary: {
    attempted: number;
    detected: number;
    failed: number;
    cancelled: number;
    p50_ms: number | null;
    p95_ms: number | null;
  };
  samples: {
    status: ReceiverStatus;
    elapsed_ms: number | null;
    poll_interval_ms: number | null;
    created_at: string;
  }[];
}

/** Select only this listener, recompute counts and whitelist export fields. No provider operations. */
export function receiverProbeReport(
  value: unknown,
  listenerId: string,
): ReceiverProbeReport | null {
  const raw = object(value);
  const measurement = object(raw?.measurement);
  if (
    !raw ||
    !listenerId ||
    measurement?.boundary !== PROBE_MEASUREMENT ||
    measurement.clock !== 'single_browser_monotonic' ||
    measurement.client_reported !== true ||
    measurement.physical_speaker_output_measured !== false ||
    measurement.translation_end_to_end_measured !== false ||
    typeof raw.generated_at !== 'string' ||
    !Number.isFinite(Date.parse(raw.generated_at)) ||
    !Array.isArray(raw.samples) ||
    raw.samples.length > 1000
  )
    return null;
  const selected: ReceiverProbeReport['samples'] = [];
  const ids = new Set<string>();
  for (const entry of raw.samples) {
    const row = object(entry);
    if (!row || typeof row.listener_id !== 'string') return null;
    if (row.listener_id !== listenerId) continue;
    if (
      typeof row.probe_id !== 'string' ||
      !row.probe_id ||
      ids.has(row.probe_id) ||
      row.measurement !== PROBE_MEASUREMENT ||
      !statuses.includes(row.status as ReceiverStatus) ||
      (row.status === 'detected' ? !time(row.elapsed_ms) : row.elapsed_ms !== null) ||
      !(
        row.poll_interval_ms === null ||
        (time(row.poll_interval_ms) && row.poll_interval_ms <= 1000)
      ) ||
      typeof row.created_at !== 'string' ||
      !Number.isFinite(Date.parse(row.created_at))
    )
      return null;
    ids.add(row.probe_id);
    selected.push({
      status: row.status as ReceiverStatus,
      elapsed_ms: row.elapsed_ms as number | null,
      poll_interval_ms: row.poll_interval_ms as number | null,
      created_at: row.created_at,
    });
  }
  const values = selected
    .filter((row) => row.status === 'detected')
    .map((row) => row.elapsed_ms!)
    .sort((a, b) => a - b);
  const percentile = (p: number) =>
    values.length ? values[Math.max(0, Math.ceil(values.length * p) - 1)] : null;
  return {
    schema_version: 1,
    record_type: 'receiver_audio_probe_metrics',
    generated_at: raw.generated_at,
    measurement: {
      boundary: PROBE_MEASUREMENT,
      clock: 'single_browser_monotonic',
      client_reported: true,
      physical_speaker_output_measured: false,
      translation_end_to_end_measured: false,
    },
    summary: {
      attempted: selected.length,
      detected: values.length,
      failed: selected.filter((row) =>
        ['timeout', 'expired', 'delivery_error'].includes(row.status),
      ).length,
      cancelled: selected.filter((row) => row.status === 'cancelled').length,
      p50_ms: percentile(0.5),
      p95_ms: percentile(0.95),
    },
    samples: selected,
  };
}
