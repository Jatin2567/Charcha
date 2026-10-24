import { API_BASE } from './api';
import type { UsageKey, UsageReport, UsageResource, UsageStatus } from '../types/usage';

export const USAGE_DEFAULTS: ReadonlyArray<{
  key: UsageKey;
  label: string;
  unit: UsageResource['unit'];
  limit: number;
  setting: string;
}> = [
  {
    key: 'stt_seconds',
    label: 'Speech recognition time',
    unit: 'seconds',
    limit: 600,
    setting: 'USAGE_STT_SECONDS_PER_DAY',
  },
  {
    key: 'stt_connections',
    label: 'Recognition connections',
    unit: 'connections',
    limit: 30,
    setting: 'USAGE_STT_CONNECTIONS_PER_DAY',
  },
  {
    key: 'mt_requests',
    label: 'Translation calls',
    unit: 'requests',
    limit: 100,
    setting: 'USAGE_MT_REQUESTS_PER_DAY',
  },
  {
    key: 'mt_characters',
    label: 'Translation source text',
    unit: 'characters',
    limit: 30000,
    setting: 'USAGE_MT_CHARACTERS_PER_DAY',
  },
  {
    key: 'tts_requests',
    label: 'Speech synthesis calls',
    unit: 'requests',
    limit: 100,
    setting: 'USAGE_TTS_REQUESTS_PER_DAY',
  },
  {
    key: 'tts_characters',
    label: 'Synthesized text',
    unit: 'characters',
    limit: 30000,
    setting: 'USAGE_TTS_CHARACTERS_PER_DAY',
  },
  {
    key: 'voice_enrollments',
    label: 'Voice enrollments',
    unit: 'enrollments',
    limit: 3,
    setting: 'USAGE_VOICE_ENROLLMENTS_PER_DAY',
  },
];

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const nonnegative = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0;
const nullableNumber = (value: unknown) => value === null || nonnegative(value);

/** A zero limit stops new work. Unknown usage must never appear as zero consumed. */
export function usageStatus(used: number | null, limit: number): UsageStatus {
  if (!nonnegative(limit) || used === null || !nonnegative(used)) return 'unknown';
  if (limit === 0 || used >= limit) return 'exhausted';
  return Math.round((used / limit) * 10000) / 100 >= 80 ? 'warning' : 'available';
}

export function referenceUsage(now = new Date(), demo = false): UsageReport {
  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1));
  return {
    mode: 'demo',
    period: { date: now.toISOString().slice(0, 10), reset_at: next.toISOString() },
    enforcement: {
      enabled: true,
      persistent: false,
      status: demo ? 'demo' : 'unavailable',
      detail: demo
        ? 'Browser demonstration: no inference is sent. Server usage and configured limits are unavailable here.'
        : 'Connect the workspace service to see its configured limits and reserved usage.',
    },
    resources: USAGE_DEFAULTS.map(({ key, label, unit, limit }) => ({
      key,
      label,
      unit,
      limit,
      used: null,
      remaining: null,
      utilization_percent: null,
      status: 'unknown',
    })),
    billing: {
      balance_available: false,
      detail: 'Your actual provider balance is available only from your provider dashboard.',
    },
  };
}

export function validateUsage(value: unknown): UsageReport {
  const invalid = () => {
    throw new Error(
      'The workspace returned an invalid usage report. Update the server and refresh.',
    );
  };
  if (!record(value) || !['demo', 'live'].includes(String(value.mode))) return invalid();
  const { period, enforcement, resources, billing } = value;
  if (
    !record(period) ||
    typeof period.date !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}$/.test(period.date) ||
    !Number.isFinite(Date.parse(`${period.date}T00:00:00Z`)) ||
    new Date(`${period.date}T00:00:00Z`).toISOString().slice(0, 10) !== period.date ||
    typeof period.reset_at !== 'string' ||
    !/(?:Z|\+00:00)$/.test(period.reset_at) ||
    !Number.isFinite(Date.parse(period.reset_at))
  )
    return invalid();
  if (
    !record(enforcement) ||
    enforcement.enabled !== true ||
    typeof enforcement.persistent !== 'boolean' ||
    !['ready', 'unavailable', 'demo'].includes(String(enforcement.status)) ||
    typeof enforcement.detail !== 'string'
  )
    return invalid();
  if (!record(billing) || billing.balance_available !== false || typeof billing.detail !== 'string')
    return invalid();
  if (!Array.isArray(resources) || resources.length !== USAGE_DEFAULTS.length) return invalid();
  const seen = new Set<string>();
  for (const resource of resources) {
    if (!record(resource)) return invalid();
    const spec = USAGE_DEFAULTS.find((entry) => entry.key === resource.key);
    if (
      !spec ||
      seen.has(spec.key) ||
      resource.unit !== spec.unit ||
      typeof resource.label !== 'string' ||
      !nonnegative(resource.limit) ||
      !nullableNumber(resource.used) ||
      !nullableNumber(resource.remaining) ||
      !nullableNumber(resource.utilization_percent) ||
      !['available', 'warning', 'exhausted', 'unknown'].includes(String(resource.status))
    )
      return invalid();
    seen.add(spec.key);
    const used = resource.used as number | null;
    if (used === null) {
      if (
        resource.remaining !== null ||
        resource.utilization_percent !== null ||
        resource.status !== 'unknown'
      )
        return invalid();
    } else {
      if (
        resource.remaining !== Math.max(0, resource.limit - used) ||
        resource.status !== usageStatus(used, resource.limit)
      )
        return invalid();
      if (resource.utilization_percent === null) {
        if (resource.limit > 0) return invalid();
      } else if (
        resource.limit > 0 &&
        Math.abs((resource.utilization_percent as number) - (used / resource.limit) * 100) > 0.11
      )
        return invalid();
    }
  }
  return value as unknown as UsageReport;
}

/** Summary polling reads our ledger only; it never invokes a paid AI endpoint. */
export async function fetchUsage(signal: AbortSignal): Promise<UsageReport> {
  const response = await fetch(`${API_BASE}/usage`, {
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`Usage summary unavailable (${response.status}).`);
  return validateUsage(await response.json());
}
