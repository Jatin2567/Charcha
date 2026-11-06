import { afterEach, describe, expect, it, vi } from 'vitest';
import { request } from './api';
afterEach(() => vi.unstubAllGlobals());
describe('optional telemetry request cancellation', () => {
  it('honors the caller abort signal rather than leaving a calibration request running', async () => {
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal!.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError')));
    })));
    const controller = new AbortController();
    const pending = request('/test-fixture', { signal: controller.signal });
    const checked = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort();
    await checked;
  });
});
