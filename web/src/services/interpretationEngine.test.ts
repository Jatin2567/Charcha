import { beforeEach, describe, expect, it, vi } from 'vitest';
import { request } from './api';
import { engineScopeLabel, engineStatus, ensureEngine } from './interpretationEngine';
import type { Membership } from '../types/domain';

vi.mock('./api', () => ({ request: vi.fn() }));
const membership = {
  room: { code: 'meeting', engine_on_demand: true },
  session_token: 'seat',
} as Membership;
const ready = { state: 'ready', lifecycle: 'meeting', active_meetings: 1 };

describe('meeting-held interpretation readiness', () => {
  beforeEach(() => vi.mocked(request).mockReset());
  it('uses the selected room endpoint instead of the shared account status when a membership exists', async () => {
    vi.mocked(request).mockResolvedValue(ready);
    await engineStatus(membership);
    expect(request).toHaveBeenCalledWith('/rooms/meeting/engine', {}, 'seat');
    await engineStatus();
    expect(request).toHaveBeenLastCalledWith('/account/interpretation-engine', {}, undefined);
  });
  it('labels personal, multiple and unreported scopes without claiming one shared GPU', () => {
    expect(engineScopeLabel({ state: 'ready', scope: 'reviewer' })).toContain(
      'Your reviewer resources',
    );
    expect(engineScopeLabel({ state: 'external', scope: 'multiple' })).toBe(
      'Multiple reviewer engines',
    );
    expect(engineScopeLabel({ state: 'ready' })).toContain('scope not reported');
    expect(engineScopeLabel({ state: 'ready', scope: 'reviewer' }, true)).toContain(
      'Current meeting',
    );
  });

  it('repeated unmute in a ready meeting only reads status, without startup requests', async () => {
    vi.mocked(request).mockResolvedValue(ready);
    for (let i = 0; i < 12; i++) await ensureEngine(membership, () => true);
    expect(request).toHaveBeenCalledTimes(12);
    expect(vi.mocked(request).mock.calls.every(([, options]) => !options?.method)).toBe(true);
  });

  it.each(['idle', 'unavailable'])(
    'nudges startup once for %s, then uses the shared ready engine',
    async (state) => {
      vi.mocked(request)
        .mockResolvedValueOnce({ state, lifecycle: 'meeting', active_meetings: 0 })
        .mockResolvedValue(ready);
      await ensureEngine(membership, () => true);
      expect(request).toHaveBeenCalledTimes(2);
      expect(request).toHaveBeenLastCalledWith('/rooms/meeting/engine', { method: 'POST' }, 'seat');
    },
  );

  it('does not reuse a previous meeting readiness observation without renewing occupancy', async () => {
    vi.mocked(request)
      .mockResolvedValueOnce({ ...ready, active_meetings: 0 })
      .mockResolvedValue(ready);
    await ensureEngine(membership, () => true);
    expect(request).toHaveBeenLastCalledWith('/rooms/meeting/engine', { method: 'POST' }, 'seat');
  });
});
