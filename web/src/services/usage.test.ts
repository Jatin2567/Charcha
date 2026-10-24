import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  balanceSnapshotIsStale,
  fetchUsage,
  referenceUsage,
  speechFlowReferenceCost,
  usageStatus,
  validateUsage,
} from './usage';
import type { FlowResources, ProgrammePricing, ProviderFlow, UsageReport } from '../types/usage';

const liveReport = (): UsageReport => {
  const report = referenceUsage(new Date('2026-10-24T20:30:00Z'));
  report.mode = 'live';
  report.enforcement = {
    enabled: true,
    persistent: true,
    status: 'ready',
    detail: 'Daily caps active.',
  };
  report.resources = report.resources.map((resource) => ({
    ...resource,
    used: 0,
    remaining: resource.limit,
    utilization_percent: 0,
    status: 'available',
  }));
  return report;
};
afterEach(() => vi.unstubAllGlobals());

describe('daily usage evidence', () => {
  it('uses UTC calendar rollover independently of local time', () => {
    const report = referenceUsage(new Date('2026-10-24T23:59:59Z'));
    expect(report.period).toEqual({ date: '2026-10-24', reset_at: '2026-10-25T00:00:00.000Z' });
  });
  it('never invents zero consumption or a remaining balance while offline', () => {
    const report = validateUsage(referenceUsage());
    expect(report.enforcement.status).toBe('unavailable');
    expect(report.billing.balance_available).toBe(false);
    expect(report.resources).toHaveLength(7);
    expect(
      report.resources.every(
        (r) =>
          r.used === null &&
          r.remaining === null &&
          r.utilization_percent === null &&
          r.status === 'unknown',
      ),
    ).toBe(true);
  });
  it('labels the browser demo as reference data without manufacturing measurements', () => {
    const report = referenceUsage(new Date(), true);
    expect(report.enforcement.status).toBe('demo');
    expect(report.resources[0]).toMatchObject({ limit: 600, used: null, remaining: null });
    expect(report.resources.at(-1)?.limit).toBe(3);
  });
  it('warns at 80 percent and blocks a zero cap or an exhausted cap', () => {
    expect(usageStatus(79, 100)).toBe('available');
    expect(usageStatus(80, 100)).toBe('warning');
    expect(usageStatus(100, 100)).toBe('exhausted');
    expect(usageStatus(23999, 30000)).toBe('warning');
    expect(usageStatus(0, 0)).toBe('exhausted');
    expect(usageStatus(null, 0)).toBe('unknown');
    expect(usageStatus(Infinity, 100)).toBe('unknown');
    expect(usageStatus(0, -1)).toBe('unknown');
  });
  it('accepts a valid live summary and a zero-cap resource', () => {
    const report = liveReport();
    report.resources[0] = {
      ...report.resources[0],
      limit: 0,
      remaining: 0,
      utilization_percent: 100,
      status: 'exhausted',
    };
    expect(validateUsage(report)).toEqual(report);
  });
  it('accepts consumption over a lowered cap without making remaining units negative', () => {
    const report = liveReport();
    report.resources[0] = {
      ...report.resources[0],
      used: 80,
      limit: 60,
      remaining: 0,
      utilization_percent: 133.33,
      status: 'exhausted',
    };
    expect(validateUsage(report)).toEqual(report);
  });
  it.each([-1, Infinity, NaN, '42'])(
    'rejects malformed or negative resource limits (%s)',
    (limit) => {
      const report = liveReport();
      (report.resources[0] as unknown as Record<string, unknown>).limit = limit;
      expect(() => validateUsage(report)).toThrow('invalid usage report');
    },
  );
  it('rejects counters that claim known remaining units when consumption is unknown', () => {
    const report = referenceUsage();
    report.resources[0].remaining = 600;
    expect(() => validateUsage(report)).toThrow('invalid usage report');
  });
  it('rejects inconsistent warnings, remaining units and duplicate resource keys', () => {
    const report = liveReport();
    report.resources[0].status = 'warning';
    expect(() => validateUsage(report)).toThrow();
    report.resources[0].status = 'available';
    report.resources[0].remaining = 1;
    expect(() => validateUsage(report)).toThrow();
    report.resources[0].remaining = 600;
    report.resources[1] = report.resources[0];
    expect(() => validateUsage(report)).toThrow();
  });
  it('rejects incomplete reports, invalid dates and provider-balance claims', () => {
    expect(() => validateUsage({ mode: 'live' })).toThrow();
    const report = liveReport();
    report.period.date = '2026-02-30';
    expect(() => validateUsage(report)).toThrow();
    report.period.date = '2026-10-24';
    (report.billing as unknown as Record<string, unknown>).balance_available = true;
    expect(() => validateUsage(report)).toThrow();
  });
  it('fetches only the read-only summary and forwards the cancellation signal', async () => {
    const controller = new AbortController();
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => liveReport() });
    vi.stubGlobal('fetch', fetcher);
    const report = await fetchUsage(controller.signal);
    expect(report.mode).toBe('live');
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith('/api/usage', {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
  });
  it('rejects an HTTP error or malformed fetch response instead of falling back to zero', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    await expect(fetchUsage(new AbortController().signal)).rejects.toThrow('503');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }),
    );
    await expect(fetchUsage(new AbortController().signal)).rejects.toThrow('invalid usage report');
  });
});

const evidenceNow = new Date('2026-10-24T12:00:00Z');
const resources = (value: number): FlowResources =>
  Object.fromEntries(referenceUsage().resources.map(({ key }) => [key, value])) as FlowResources;
const closedFlow = (): ProviderFlow => ({
  id: 'flow_123',
  purpose: 'gnani_speech_check',
  status: 'closed',
  started_at: '2026-10-24T10:00:00Z',
  expires_at: '2026-10-24T10:01:00Z',
  closed_at: '2026-10-24T10:00:30Z',
  budgets: resources(10),
  used: resources(1),
  balance_unit: null,
  balance_delta: null,
  credits_used: null,
  credits_source: 'unknown',
  before_balance: null,
  before_observed_at: null,
  after_balance: null,
  after_observed_at: null,
  metrics: {},
});
const reconciledFlow = (unit: 'INR' | 'programme_credits' = 'programme_credits'): ProviderFlow => ({
  ...closedFlow(),
  balance_unit: unit,
  balance_delta: 0.6,
  credits_used: unit === 'programme_credits' ? 0.6 : null,
  credits_source: 'manual_dashboard_delta',
  before_balance: 3500,
  before_observed_at: '2026-10-24T09:59:00Z',
  after_balance: 3499.4,
  after_observed_at: '2026-10-24T10:01:00Z',
});

describe('bounded flow permissions and programme balance evidence', () => {
  it('defaults an older server to locked permission and unknown balance', () => {
    const old = liveReport() as unknown as Record<string, unknown>;
    delete old.approval;
    delete old.programme;
    const clean = validateUsage(old, evidenceNow);
    expect(clean.approval).toMatchObject({
      required: true,
      status: 'locked',
      active_flow_id: null,
    });
    expect(clean.programme).toMatchObject({ balance: null, automatic_sync: false, flows: [] });
  });
  it('keeps the static demo empty without inventing a balance or paid tests', () => {
    const demo = validateUsage(referenceUsage(evidenceNow, true), evidenceNow);
    expect(demo.approval.status).toBe('demo');
    expect(demo.programme.balance).toBeNull();
    expect(demo.programme.flows).toEqual([]);
  });
  it('accepts only a live, required, unexpired approval with a flow reference', () => {
    const report = liveReport();
    report.approval = {
      required: true,
      status: 'approved',
      active_flow_id: 'flow_123',
      expires_at: '2026-10-24T13:00:00Z',
      detail: 'One written approval recorded.',
    };
    expect(validateUsage(report, evidenceNow).approval.status).toBe('approved');
    report.approval.active_flow_id = null;
    expect(() => validateUsage(report, evidenceNow)).toThrow();
    report.approval.active_flow_id = 'flow_123';
    report.approval.required = false;
    expect(() => validateUsage(report, evidenceNow)).toThrow();
    report.approval.required = true;
    report.mode = 'demo';
    expect(() => validateUsage(report, evidenceNow)).toThrow();
  });
  it('locks an approval after its expiry even if the server snapshot still says approved', () => {
    const report = liveReport();
    report.approval = {
      required: true,
      status: 'approved',
      active_flow_id: 'flow_123',
      expires_at: '2026-10-24T12:00:00Z',
      detail: 'Expired snapshot.',
    };
    expect(validateUsage(report, evidenceNow).approval).toMatchObject({
      status: 'locked',
      active_flow_id: null,
      expires_at: null,
    });
  });
  it('keeps a user-reported rupee balance separate from programme credits and quoted pricing', () => {
    const report = liveReport();
    report.programme = {
      ...report.programme,
      source: 'user_reported',
      unit: 'INR',
      balance: 3500,
      observed_at: evidenceNow.toISOString(),
      quoted_rate: {
        amount: 0.06,
        currency: 'INR',
        unit: 'request',
        source: 'user_reported',
        scope: 'unconfirmed',
      },
    };
    const clean = validateUsage(report, evidenceNow).programme;
    expect(clean.balance).toBe(3500);
    expect(clean.unit).toBe('INR');
    expect(clean.quoted_rate?.scope).toBe('unconfirmed');
    expect(clean.flows).toEqual([]);
    expect(clean.automatic_sync).toBe(false);
  });
  it('requires dated, finite, nonnegative manual evidence and rejects invented automatic sync', () => {
    for (const patch of [
      {
        source: 'manual_dashboard',
        unit: 'INR',
        balance: -1,
        observed_at: evidenceNow.toISOString(),
      },
      { source: 'manual_dashboard', unit: 'INR', balance: 3500, observed_at: null },
      {
        source: 'manual_dashboard',
        unit: 'INR',
        balance: Infinity,
        observed_at: evidenceNow.toISOString(),
      },
      {
        source: 'manual_dashboard',
        unit: 'INR',
        balance: 3500,
        observed_at: '2026-10-25T12:00:00Z',
      },
      { source: 'not_connected', unit: null, balance: 3500, observed_at: null },
      { automatic_sync: true },
      { source: 'provider_api' },
    ]) {
      const report = liveReport();
      Object.assign(report.programme, patch);
      expect(() => validateUsage(report, evidenceNow)).toThrow();
    }
  });
  it('marks old snapshots as historical without pretending to update their balance', () => {
    expect(balanceSnapshotIsStale('2026-10-23T12:00:00Z', evidenceNow)).toBe(false);
    expect(balanceSnapshotIsStale('2026-10-23T11:59:59Z', evidenceNow)).toBe(true);
    expect(balanceSnapshotIsStale(null, evidenceNow)).toBe(true);
    expect(balanceSnapshotIsStale('invalid', evidenceNow)).toBe(true);
  });
  it('retains unknown per-flow credits after actual reservations until reconciliation', () => {
    const report = liveReport();
    report.programme.flows = [closedFlow()];
    const flow = validateUsage(report, evidenceNow).programme.flows[0];
    expect(flow.used.tts_requests).toBe(1);
    expect(flow.credits_used).toBeNull();
    expect(flow.balance_delta).toBeNull();
    expect(flow.credits_source).toBe('unknown');
  });
  it('accepts a manual difference in credits or rupees without converting currencies', () => {
    const report = liveReport();
    report.programme.flows = [reconciledFlow()];
    expect(validateUsage(report, evidenceNow).programme.flows[0].credits_used).toBe(0.6);
    report.programme.flows = [reconciledFlow('INR')];
    const money = validateUsage(report, evidenceNow).programme.flows[0];
    expect(money.balance_delta).toBe(0.6);
    expect(money.credits_used).toBeNull();
    expect(money.balance_unit).toBe('INR');
  });
  it('rejects top-ups, wrong deltas, premature snapshots, fabricated credits and over-budget work', () => {
    for (const patch of [
      { after_balance: 3501, balance_delta: 1 },
      { balance_delta: 1 },
      { before_observed_at: '2026-10-24T10:00:01Z' },
      { after_observed_at: '2026-10-24T10:00:01Z' },
      { balance_unit: 'INR', credits_used: 0.6 },
      { credits_source: 'unknown', credits_used: 0.6 },
      { used: resources(11) },
      { budgets: { ...resources(10), stt_seconds: -1 } },
    ]) {
      const report = liveReport();
      report.programme.flows = [Object.assign(reconciledFlow(), patch)];
      expect(() => validateUsage(report, evidenceNow)).toThrow();
    }
  });
  it('rejects duplicate flow references or unbounded history', () => {
    const report = liveReport();
    report.programme.flows = [closedFlow(), closedFlow()];
    expect(() => validateUsage(report, evidenceNow)).toThrow();
    report.programme.flows = Array.from({ length: 51 }, (_, index) => ({
      ...closedFlow(),
      id: `flow_${index}`,
    }));
    expect(() => validateUsage(report, evidenceNow)).toThrow();
  });
  it('keeps only safe numeric measurements, rejects invalid timing and strips hidden fields before export', () => {
    const report = liveReport();
    report.programme.flows = [closedFlow()];
    Object.assign(report.programme.flows[0].metrics, {
      tts_first_pcm_ms: 123.5,
      tts_audio_seconds: 2,
      error_stage: 'none',
      transcript: 'private speech',
      api_key: 'private key',
    });
    Object.assign(report, { api_key: 'private key' });
    Object.assign(report.programme.flows[0], { audio: 'private audio' });
    report.approval.detail = 'Invalid credential vach_this_is_test or Bearer secret.test';
    const clean = validateUsage(report, evidenceNow);
    const exported = JSON.stringify(clean);
    expect(clean.programme.flows[0].metrics).toEqual({
      tts_first_pcm_ms: 123.5,
      tts_audio_seconds: 2,
      error_stage: 'none',
    });
    expect(exported).not.toMatch(
      /private key|private audio|private speech|vach_this_is_test|secret\.test/,
    );
    report.programme.flows[0].metrics.tts_first_pcm_ms = -1;
    expect(() => validateUsage(report, evidenceNow)).toThrow();
  });
});

const suppliedPricing = (): ProgrammePricing => ({
  currency: 'INR',
  source: 'user_provided_pricing_table',
  reference_url: 'https://app.gnani.ai/voice/pricing',
  stt_per_hour: 27,
  tts_per_10000_characters: 27,
  voice_enrollment: null,
  rounding: 'unconfirmed',
});

describe('service-specific speech pricing references', () => {
  it('keeps supplied time/character tariffs as references without deducting any account balance', () => {
    const report = liveReport();
    report.programme.pricing = suppliedPricing();
    report.programme.flows = [
      {
        ...closedFlow(),
        used: { ...resources(0), stt_seconds: 4, tts_characters: 12 },
        budgets: resources(20),
      },
    ];
    const clean = validateUsage(report, evidenceNow);
    expect(speechFlowReferenceCost(clean.programme.flows[0], clean.programme.pricing)).toBeCloseTo(
      0.0624,
    );
    expect(clean.programme.balance).toBeNull();
    expect(clean.programme.flows[0].credits_used).toBeNull();
    expect(clean.programme.flows[0].balance_delta).toBeNull();
    expect(clean.programme.pricing?.rounding).toBe('unconfirmed');
  });
  it('never estimates cloning, live interpretation or missing-service pricing from a flat request quote', () => {
    const flow = { ...closedFlow(), used: resources(0) };
    expect(
      speechFlowReferenceCost({ ...flow, purpose: 'voice_clone_check' }, suppliedPricing()),
    ).toBeNull();
    expect(
      speechFlowReferenceCost({ ...flow, purpose: 'live_interpretation' }, suppliedPricing()),
    ).toBeNull();
    expect(speechFlowReferenceCost(flow, null)).toBeNull();
    expect(speechFlowReferenceCost(flow, { ...suppliedPricing(), stt_per_hour: null })).toBeNull();
    expect(
      speechFlowReferenceCost(
        { ...flow, used: { ...resources(0), voice_enrollments: 1 } },
        suppliedPricing(),
      ),
    ).toBeNull();
  });
  it('rejects unverified origins, negative rates and asserted cloning or rounding prices', () => {
    for (const patch of [
      { source: 'provider_invoice' },
      { reference_url: 'https://example.com/prices' },
      { stt_per_hour: -27 },
      { tts_per_10000_characters: Infinity },
      { voice_enrollment: 0.06 },
      { rounding: 'confirmed' },
    ]) {
      const report = liveReport();
      report.programme.pricing = Object.assign(suppliedPricing(), patch);
      expect(() => validateUsage(report, evidenceNow)).toThrow();
    }
  });
});
