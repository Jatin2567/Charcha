import { afterEach, describe, expect, it, vi } from 'vitest';
import { checkHealth, isLocalDemo } from './api';
import { LANGUAGES } from '../types/domain';

afterEach(() => vi.unstubAllGlobals());

describe('workspace health mode detection', () => {
  it('accepts a transport-only backend and its disabled paid providers without demo fallback', async () => {
    const health = {
      status: 'ok',
      mode: 'transport',
      version: '0.1.0',
      languages: [],
      providers: [
        { name: 'LiveKit', status: 'configured', detail: 'Local original audio only' },
        {
          name: 'Prisma STT',
          status: 'disabled',
          detail: 'No provider requests in transport mode',
        },
      ],
    };
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(health), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    expect(await checkHealth()).toEqual(health);
    expect(isLocalDemo()).toBe(false);
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe('/api/health');
  });
  it('rejects a malformed service response rather than labelling it a connected workspace', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            mode: 'transport',
            providers: [null],
            languages: [],
          }),
          { status: 200 },
        ),
      ),
    );
    await expect(checkHealth()).rejects.toThrow('workspace service is unavailable');
  });
  it('recognizes the expanded service catalog while rejecting a language outside the shared speech flow', async () => {
    const health = {
      status: 'ok',
      mode: 'live',
      version: 'test',
      providers: [],
      languages: LANGUAGES.map((language) => ({
        code: language.code,
        name: language.name,
        native_name: language.native,
      })),
    };
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(health), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...health,
            languages: [{ code: 'or', name: 'Odia', native_name: 'ଓଡ଼ିଆ' }],
          }),
          { status: 200 },
        ),
      );
    vi.stubGlobal('fetch', fetch);
    expect((await checkHealth()).languages).toHaveLength(10);
    await expect(checkHealth()).rejects.toThrow('workspace service is unavailable');
  });
});
