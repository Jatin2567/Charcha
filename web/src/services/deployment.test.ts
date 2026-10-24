import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEPLOYMENT_FIELDS, fetchDeployment, validateDeployment } from './deployment';
import { referenceReadiness } from './performance';

afterEach(() => vi.unstubAllGlobals());

describe('deployment configuration evidence', () => {
  it('retains only known setting names and booleans, never server-returned values', () => {
    const report = referenceReadiness();
    report.mode = 'live';
    report.requirements[0].configured = true;
    const snapshot = validateDeployment({
      ...report,
      secret: 'must-not-survive',
      requirements: report.requirements.map((field) => ({ ...field, value: 'private-value' })),
    });
    expect(snapshot.fields).toHaveLength(9);
    expect(snapshot.fields[0]).toEqual({ key: 'GNANI_API_KEY', configured: true });
    expect(JSON.stringify(snapshot)).not.toContain('private-value');
    expect(JSON.stringify(snapshot)).not.toContain('must-not-survive');
    expect(snapshot.mode).toBe('live');
  });
  it('preserves demo mode and represents missing optional settings as unknown', () => {
    const report = referenceReadiness();
    report.requirements = report.requirements.filter((field) => field.required);
    const snapshot = validateDeployment(report);
    expect(snapshot.mode).toBe('demo');
    expect(snapshot.fields.filter((field) => field.configured === false)).toHaveLength(6);
    expect(snapshot.fields.filter((field) => field.configured === null)).toHaveLength(3);
  });
  it('rejects incomplete, duplicate or non-boolean configuration evidence', () => {
    const report = referenceReadiness();
    expect(() => validateDeployment({ ...report, requirements: [] })).toThrow();
    expect(() =>
      validateDeployment({
        ...report,
        requirements: [...report.requirements, report.requirements[0]],
      }),
    ).toThrow();
    expect(() =>
      validateDeployment({
        ...report,
        requirements: report.requirements.map((field) => ({ ...field, configured: 'true' })),
      }),
    ).toThrow();
  });
  it('rejects unsupported modes, invalid dates and a claim that provider access was tested', () => {
    const report = referenceReadiness();
    expect(() => validateDeployment({ ...report, mode: 'production-ready' })).toThrow();
    expect(() => validateDeployment({ ...report, generated_at: 'yesterday' })).toThrow();
    expect(() => validateDeployment({ ...report, provider_verification: 'verified' })).toThrow();
  });
  it('retains only recognised static configuration issues and rejects malformed issue metadata', () => {
    const report = referenceReadiness();
    const snapshot = validateDeployment({
      ...report,
      configuration_issues: [
        {
          key: 'CORS_ORIGINS',
          detail: 'Use a secure explicit application origin.',
          extra: 'discard-me',
        },
        { key: 'PRIVATE_VALUE', detail: 'unknown-field-discarded' },
      ],
    });
    expect(snapshot.configuration_issues).toEqual([
      { key: 'CORS_ORIGINS', detail: 'Use a secure explicit application origin.' },
    ]);
    expect(() =>
      validateDeployment({ ...report, configuration_issues: [{ key: 'CORS_ORIGINS' }] }),
    ).toThrow();
    expect(() => validateDeployment({ ...report, configuration_issues: 'invalid' })).toThrow();
  });
  it('fetches only the read-only readiness endpoint and forwards cancellation', async () => {
    const controller = new AbortController();
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => referenceReadiness() });
    vi.stubGlobal('fetch', fetcher);
    await fetchDeployment(controller.signal);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toMatch(/\/api\/readiness$/);
    expect(fetcher.mock.calls[0][1]).toEqual({
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
    });
    expect(DEPLOYMENT_FIELDS.filter((field) => field.required)).toHaveLength(6);
  });
  it('leaves unavailable or malformed services as errors without inventing a configured report', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    await expect(fetchDeployment(new AbortController().signal)).rejects.toThrow();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ mode: 'live' }) }),
    );
    await expect(fetchDeployment(new AbortController().signal)).rejects.toThrow();
  });
});
