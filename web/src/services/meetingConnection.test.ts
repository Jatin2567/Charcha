import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Membership } from '../types/domain';
import { request } from './api';
import { refreshMeetingConnection } from './meetingConnection';

vi.mock('./api', () => ({ request: vi.fn() }));
const seat = {
  room: { code: 'room123', mode: 'live' }, participant: { id: 'same-seat', voice_mode: 'cloned' },
  session_token: 'membership', livekit: { url: 'wss://local.test', token: 'expired-media', agent_identity: 'agent' },
} as Membership;
const fresh = { ...seat, livekit: { ...seat.livekit!, token: 'fresh-media' } };

describe('refreshing an admitted meeting connection', () => {
  beforeEach(() => { vi.mocked(request).mockReset(); });

  it('replaces a cached media token without changing the admitted seat or voice', async () => {
    vi.mocked(request).mockResolvedValue(fresh);
    const signal = new AbortController().signal;
    const restored = await refreshMeetingConnection(seat, signal);
    expect(request).toHaveBeenCalledExactlyOnceWith('/rooms/room123/connection',
      { method: 'POST', signal }, 'membership');
    expect(restored.livekit?.token).toBe('fresh-media');
    expect(restored.participant).toBe(seat.participant);
    expect(restored.session_token).toBe(seat.session_token);
  });

  it('obtains a fresh credential on every new connection, never falling back to cached media', async () => {
    vi.mocked(request).mockResolvedValueOnce(fresh)
      .mockResolvedValueOnce({ ...fresh, livekit: { ...fresh.livekit, token: 'next-media' } });
    await refreshMeetingConnection(seat);
    expect((await refreshMeetingConnection(fresh)).livekit?.token).toBe('next-media');
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('does not revive expired or revoked membership or retry its old media token', async () => {
    vi.mocked(request).mockRejectedValue(new Error('Membership expired; rejoin the conversation'));
    await expect(refreshMeetingConnection(seat)).rejects.toThrow('Membership expired');
    expect(request).toHaveBeenCalledTimes(1);
  });

  it.each([
    { ...fresh, participant: { ...seat.participant, id: 'another-seat' } },
    { ...fresh, room: { ...seat.room, code: 'another-room' } },
    { ...fresh, session_token: 'another-membership' },
    { ...fresh, livekit: null },
  ])('rejects a response for a different membership or missing media', async (result) => {
    vi.mocked(request).mockResolvedValue(result);
    await expect(refreshMeetingConnection(seat)).rejects.toThrow('could not be restored');
  });

  it('discards a late response after the connection was cancelled', async () => {
    const controller = new AbortController();
    vi.mocked(request).mockImplementation(async () => { controller.abort(); return fresh; });
    await expect(refreshMeetingConnection(seat, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('keeps scripted demonstrations offline', async () => {
    const demo = { ...seat, room: { ...seat.room, mode: 'demo' as const } };
    expect(await refreshMeetingConnection(demo)).toBe(demo);
    expect(request).not.toHaveBeenCalled();
  });
});
