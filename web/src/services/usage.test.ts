import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchUsage, referenceUsage, usageStatus, validateUsage } from './usage';
import type { UsageReport } from '../types/usage';

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
    expect(validateUsage(report)).toBe(report);
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
    expect(validateUsage(report)).toBe(report);
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
