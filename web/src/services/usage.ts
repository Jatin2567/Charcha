import { API_BASE } from './api';
import type {
  BalanceUnit,
  FlowApproval,
  FlowMetrics,
  FlowResources,
  ProgrammePricing,
  ProgrammeUsage,
  ProviderFlow,
  UsageKey,
  UsageReport,
  UsageResource,
  UsageStatus,
} from '../types/usage';

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
const timestamp = (value: unknown): value is string =>
  typeof value === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value) &&
  Number.isFinite(Date.parse(value)) &&
  new Date(value).toISOString().slice(0, 10) === value.slice(0, 10);
const creditNumber = (value: unknown): value is number => nonnegative(value) && value <= 1e12;
const balanceUnit = (value: unknown): value is BalanceUnit =>
  value === 'INR' || value === 'programme_credits';
const safeText = (value: string) =>
  value
    .replace(/vach_[A-Za-z0-9_-]+/gi, '[redacted credential]')
    .replace(/\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi, '[redacted credential]')
    .slice(0, 1200);

function lockedApproval(): FlowApproval {
  return {
    required: true,
    status: 'locked',
    active_flow_id: null,
    expires_at: null,
    detail: 'A separate owner-approved, bounded flow is required before any provider use.',
  };
}

function unknownProgramme(): ProgrammeUsage {
  return {
    source: 'not_connected',
    unit: null,
    balance: null,
    observed_at: null,
    automatic_sync: false,
    detail:
      'No dashboard balance has been recorded. Automatic provider balance sync is unavailable.',
    quoted_rate: null,
    pricing: null,
    flows: [],
  };
}

/** Dashboard snapshots become historical evidence after a day, never a live balance. */
export function balanceSnapshotIsStale(observedAt: string | null, now = new Date()): boolean {
  return !observedAt || !timestamp(observedAt) || now.getTime() - Date.parse(observedAt) > 86400000;
}

/** A pricing reference for reserved units, never a provider debit or balance adjustment. */
export function speechFlowReferenceCost(
  flow: ProviderFlow,
  pricing: ProgrammePricing | null,
): number | null {
  if (
    flow.purpose !== 'gnani_speech_check' ||
    flow.used.voice_enrollments > 0 ||
    !pricing ||
    pricing.stt_per_hour === null ||
    pricing.tts_per_10000_characters === null
  )
    return null;
  return (
    (flow.used.stt_seconds * pricing.stt_per_hour) / 3600 +
    (flow.used.tts_characters * pricing.tts_per_10000_characters) / 10000
  );
}

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
    approval: {
      ...lockedApproval(),
      status: demo ? 'demo' : 'locked',
    },
    programme: unknownProgramme(),
  };
}

export function validateUsage(value: unknown, now = new Date()): UsageReport {
  const invalid = () => {
    throw new Error(
      'The workspace returned an invalid usage report. Update the server and refresh.',
    );
  };
  if (!record(value) || !['demo', 'live', 'transport'].includes(String(value.mode))) return invalid();
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
    !['ready', 'unavailable', 'demo', 'disabled'].includes(String(enforcement.status)) ||
    (enforcement.status === 'disabled' && value.mode !== 'transport') ||
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
  const approval = validateApproval(
    value.approval,
    value.mode as UsageReport['mode'],
    now,
    invalid,
  );
  const programme = validateProgramme(value.programme, now, invalid);
  // Keep only documented fields. Server diagnostics or credentials must never enter UI exports.
  return {
    mode: value.mode as UsageReport['mode'],
    period: { date: period.date, reset_at: period.reset_at },
    enforcement: {
      enabled: true,
      persistent: enforcement.persistent,
      status: enforcement.status as UsageReport['enforcement']['status'],
      detail: safeText(enforcement.detail),
    },
    resources: resources.map((resource) => {
      const item = resource as unknown as UsageResource;
      return {
        key: item.key,
        label: safeText(item.label),
        unit: item.unit,
        used: item.used,
        limit: item.limit,
        remaining: item.remaining,
        utilization_percent: item.utilization_percent,
        status: item.status,
      };
    }),
    billing: { balance_available: false, detail: safeText(billing.detail) },
    approval,
    programme,
  };
}

function validateApproval(
  value: unknown,
  mode: UsageReport['mode'],
  now: Date,
  invalid: () => never,
): FlowApproval {
  // An older server cannot silently turn the new approval gate off.
  if (value === undefined) return lockedApproval();
  if (
    !record(value) ||
    typeof value.required !== 'boolean' ||
    !['locked', 'approved', 'unavailable', 'demo', 'disabled'].includes(String(value.status)) ||
    (value.status === 'disabled' && mode !== 'transport') ||
    typeof value.detail !== 'string' ||
    (value.active_flow_id !== null && !flowId(value.active_flow_id)) ||
    (value.expires_at !== null && !timestamp(value.expires_at))
  )
    return invalid();
  if (mode === 'live' && value.required !== true) return invalid();
  if (mode === 'live' && value.status === 'demo') return invalid();
  if (value.status === 'approved') {
    if (mode !== 'live' || !value.required || !value.active_flow_id || !value.expires_at)
      return invalid();
    if (Date.parse(value.expires_at as string) <= now.getTime())
      return {
        ...lockedApproval(),
        detail: 'The recorded flow approval has expired. Ask the owner before another flow.',
      };
  } else if (value.active_flow_id !== null || value.expires_at !== null) return invalid();
  return {
    required: value.required,
    status: value.status as FlowApproval['status'],
    active_flow_id: value.active_flow_id as string | null,
    expires_at: value.expires_at as string | null,
    detail: safeText(value.detail),
  };
}

const flowId = (value: unknown): value is string =>
  typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value) && !/^vach_/i.test(value);

function validateProgramme(value: unknown, now: Date, invalid: () => never): ProgrammeUsage {
  if (value === undefined) return unknownProgramme();
  if (
    !record(value) ||
    !['not_connected', 'manual_dashboard', 'user_reported'].includes(String(value.source)) ||
    value.automatic_sync !== false ||
    typeof value.detail !== 'string' ||
    !Array.isArray(value.flows) ||
    value.flows.length > 50
  )
    return invalid();
  if (value.source === 'not_connected') {
    if (value.balance !== null || value.observed_at !== null || value.unit !== null)
      return invalid();
  } else if (
    !creditNumber(value.balance) ||
    !balanceUnit(value.unit) ||
    !timestamp(value.observed_at) ||
    Date.parse(value.observed_at) > now.getTime() + 300000
  )
    return invalid();
  let quotedRate: ProgrammeUsage['quoted_rate'] = null;
  if (value.quoted_rate !== null) {
    const rate = value.quoted_rate;
    if (
      !record(rate) ||
      !creditNumber(rate.amount) ||
      rate.currency !== 'INR' ||
      rate.unit !== 'request' ||
      rate.source !== 'user_reported' ||
      rate.scope !== 'unconfirmed'
    )
      return invalid();
    quotedRate = {
      amount: rate.amount,
      currency: 'INR',
      unit: 'request',
      source: 'user_reported',
      scope: 'unconfirmed',
    };
  }
  let pricing: ProgrammePricing | null = null;
  if (value.pricing !== undefined && value.pricing !== null) {
    const rates = value.pricing;
    if (
      !record(rates) ||
      rates.currency !== 'INR' ||
      rates.source !== 'user_provided_pricing_table' ||
      rates.reference_url !== 'https://app.gnani.ai/voice/pricing' ||
      !(rates.stt_per_hour === null || creditNumber(rates.stt_per_hour)) ||
      !(rates.tts_per_10000_characters === null || creditNumber(rates.tts_per_10000_characters)) ||
      rates.voice_enrollment !== null ||
      rates.rounding !== 'unconfirmed'
    )
      return invalid();
    pricing = {
      currency: 'INR',
      source: 'user_provided_pricing_table',
      reference_url: 'https://app.gnani.ai/voice/pricing',
      stt_per_hour: rates.stt_per_hour,
      tts_per_10000_characters: rates.tts_per_10000_characters,
      voice_enrollment: null,
      rounding: 'unconfirmed',
    };
  }
  const seen = new Set<string>();
  const flows = value.flows.map((flow) => {
    const clean = validateFlow(flow, now, invalid);
    if (seen.has(clean.id)) return invalid();
    seen.add(clean.id);
    return clean;
  });
  return {
    source: value.source as ProgrammeUsage['source'],
    unit: value.unit as BalanceUnit | null,
    balance: value.balance as number | null,
    observed_at: value.observed_at as string | null,
    automatic_sync: false,
    detail: safeText(value.detail),
    quoted_rate: quotedRate,
    pricing,
    flows,
  };
}

function validateFlow(value: unknown, now: Date, invalid: () => never): ProviderFlow {
  if (
    !record(value) ||
    !flowId(value.id) ||
    !['gnani_speech_check', 'voice_clone_check', 'live_interpretation'].includes(
      String(value.purpose),
    ) ||
    !['approved', 'closed', 'expired', 'exhausted'].includes(String(value.status)) ||
    !timestamp(value.started_at) ||
    !timestamp(value.expires_at) ||
    Date.parse(value.expires_at) <= Date.parse(value.started_at) ||
    Date.parse(value.started_at) > now.getTime() + 300000 ||
    (value.closed_at !== null &&
      (!timestamp(value.closed_at) ||
        Date.parse(value.closed_at) < Date.parse(value.started_at) ||
        Date.parse(value.closed_at) > now.getTime() + 300000)) ||
    !['unknown', 'manual_dashboard_delta'].includes(String(value.credits_source))
  )
    return invalid();
  const cleanResources = (input: unknown): FlowResources => {
    if (!record(input)) return invalid();
    const result = {} as FlowResources;
    for (const { key } of USAGE_DEFAULTS) {
      if (!Number.isSafeInteger(input[key]) || !nonnegative(input[key])) return invalid();
      result[key] = input[key];
    }
    return result;
  };
  const budgets = cleanResources(value.budgets);
  const used = cleanResources(value.used);
  if (USAGE_DEFAULTS.some(({ key }) => used[key] > budgets[key])) return invalid();
  const before = value.before_balance;
  const after = value.after_balance;
  const beforeAt = value.before_observed_at;
  const afterAt = value.after_observed_at;
  if (before === null) {
    if (beforeAt !== null || value.balance_unit !== null || after !== null || afterAt !== null)
      return invalid();
  } else if (
    !creditNumber(before) ||
    !balanceUnit(value.balance_unit) ||
    !timestamp(beforeAt) ||
    Date.parse(beforeAt) > Date.parse(value.started_at)
  )
    return invalid();
  if (after !== null) {
    if (
      !creditNumber(after) ||
      !creditNumber(before) ||
      after > before ||
      !timestamp(afterAt) ||
      Date.parse(afterAt) < Date.parse((value.closed_at || value.expires_at) as string) ||
      Date.parse(afterAt) > now.getTime() + 300000
    )
      return invalid();
  } else if (afterAt !== null) return invalid();
  if (value.credits_source === 'unknown') {
    if (value.credits_used !== null || value.balance_delta !== null) return invalid();
  } else {
    if (
      !creditNumber(before) ||
      !creditNumber(after) ||
      !creditNumber(value.balance_delta) ||
      Math.abs(before - after - value.balance_delta) > 0.000001 ||
      (value.balance_unit === 'programme_credits'
        ? value.credits_used !== value.balance_delta
        : value.credits_used !== null)
    )
      return invalid();
  }
  const metrics: FlowMetrics = {};
  if (value.metrics !== undefined) {
    if (!record(value.metrics)) return invalid();
    for (const key of [
      'tts_first_pcm_ms',
      'tts_total_ms',
      'stt_final_ms',
      'tts_audio_seconds',
      'reference_seconds',
    ] as const) {
      const measurement = value.metrics[key];
      if (measurement !== undefined) {
        if (!nonnegative(measurement) || measurement > 1e9) return invalid();
        metrics[key] = measurement;
      }
    }
    const errorStage = value.metrics.error_stage;
    if (errorStage !== undefined) {
      if (
        !['none', 'tts', 'stt', 'enrollment', 'configuration', 'approval', 'cancelled'].includes(
          String(errorStage),
        )
      )
        return invalid();
      metrics.error_stage = errorStage as FlowMetrics['error_stage'];
    }
  }
  return {
    id: value.id,
    purpose: value.purpose as ProviderFlow['purpose'],
    status:
      value.status === 'approved' && Date.parse(value.expires_at) <= now.getTime()
        ? 'expired'
        : (value.status as ProviderFlow['status']),
    started_at: value.started_at,
    expires_at: value.expires_at,
    closed_at: value.closed_at as string | null,
    budgets,
    used,
    balance_unit: value.balance_unit as BalanceUnit | null,
    balance_delta: value.balance_delta as number | null,
    credits_used: value.credits_used as number | null,
    credits_source: value.credits_source as ProviderFlow['credits_source'],
    before_balance: before as number | null,
    before_observed_at: beforeAt as string | null,
    after_balance: after as number | null,
    after_observed_at: afterAt as string | null,
    metrics,
  };
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
