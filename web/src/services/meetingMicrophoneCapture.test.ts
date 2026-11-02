import { describe, expect, it, vi } from 'vitest';
import type { LocalAudioTrack, Room } from 'livekit-client';
import { MeetingMicrophone } from './meetingMicrophoneCapture';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
function track() {
  const events = new Map<string, () => void>();
  const raw = {
    stop: vi.fn(),
    mediaStreamTrack: {
      addEventListener: vi.fn((event: string, cb: () => void) => events.set(event, cb)),
      removeEventListener: vi.fn((event: string) => events.delete(event)),
    },
  };
  return { raw, events, value: raw as unknown as LocalAudioTrack };
}
function setup(capture?: () => Promise<LocalAudioTrack>) {
  const initial = track();
  const local = {
    publishTrack: vi.fn(async () => ({})),
    unpublishTrack: vi.fn(async () => undefined),
  };
  const changed = vi.fn();
  const acquire = vi.fn(capture ?? (async () => initial.value));
  const microphone = new MeetingMicrophone(
    { localParticipant: local } as unknown as Pick<Room, 'localParticipant'>,
    'self',
    'selected-input',
    changed,
    acquire,
  );
  return { microphone, local, changed, acquire, initial };
}

describe('explicit microphone lifecycle', () => {
  it('never captures merely because a connection is created or restored', async () => {
    const h = setup();
    await expect(h.microphone.setMuted(false)).rejects.toThrow('not connected');
    h.microphone.connected();
    await h.microphone.setMuted(true, 'initial');
    expect(h.acquire).not.toHaveBeenCalled();
    await h.microphone.setMuted(false);
    expect(h.acquire).toHaveBeenCalledWith(
      expect.objectContaining({ deviceId: { exact: 'selected-input' } }),
    );
    expect(h.local.publishTrack).toHaveBeenCalledWith(
      h.initial.value,
      expect.objectContaining({ name: 'source:self', source: 'microphone' }),
    );
    expect(h.changed).toHaveBeenLastCalledWith({ muted: false, reason: 'user' });
  });
  it('stops hardware before waiting for unpublish and reconnect never resumes it', async () => {
    const h = setup();
    h.microphone.connected();
    await h.microphone.setMuted(false);
    const lost = deferred<undefined>();
    h.local.unpublishTrack.mockImplementation(() => lost.promise);
    h.microphone.suspend('reconnecting');
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.microphone.track).toBeUndefined();
    expect(h.changed).toHaveBeenLastCalledWith({ muted: true, reason: 'reconnecting' });
    await expect(h.microphone.setMuted(false)).rejects.toThrow('not connected');
    h.microphone.connected();
    expect(h.acquire).toHaveBeenCalledTimes(1);
    lost.resolve(undefined);
    const next = track();
    h.acquire.mockResolvedValueOnce(next.value);
    await h.microphone.setMuted(false);
    expect(h.microphone.track).toBe(next.value);
  });
  it.each(['mute', 'disconnect'] as const)(
    'rejects a late device result after %s without publishing',
    async (action) => {
      const waiting = deferred<LocalAudioTrack>();
      const h = setup(() => waiting.promise);
      h.microphone.connected();
      const enabling = h.microphone.setMuted(false);
      const rejection = expect(enabling).rejects.toThrow('cancelled');
      if (action === 'mute') await h.microphone.setMuted(true);
      else h.microphone.disconnect();
      waiting.resolve(h.initial.value);
      await rejection;
      expect(h.initial.raw.stop).toHaveBeenCalled();
      expect(h.local.publishTrack).not.toHaveBeenCalled();
      expect(h.changed.mock.calls.some(([state]) => state.muted === false)).toBe(false);
    },
  );
  it('removes a late publication without announcing an unmuted microphone', async () => {
    const h = setup();
    h.microphone.connected();
    const published = deferred<object>();
    h.local.publishTrack.mockImplementation(() => published.promise);
    const enabling = h.microphone.setMuted(false);
    const rejection = expect(enabling).rejects.toThrow('cancelled');
    await Promise.resolve();
    await h.microphone.setMuted(true);
    published.resolve({});
    await rejection;
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.local.unpublishTrack).toHaveBeenCalledWith(h.initial.value);
    expect(h.changed.mock.calls.some(([state]) => state.muted === false)).toBe(false);
  });
  it('publication failure leaves hardware off and produces a safe actionable error', async () => {
    const h = setup();
    h.microphone.connected();
    h.local.publishTrack.mockRejectedValueOnce(new Error('private upstream details'));
    await expect(h.microphone.setMuted(false)).rejects.toThrow('could not start');
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.microphone.track).toBeUndefined();
    expect(h.changed).toHaveBeenLastCalledWith({ muted: true, reason: 'error' });
  });
  it('a missing or unplugged device reports a muted state and permits explicit retry', async () => {
    const h = setup();
    h.microphone.connected();
    await h.microphone.setMuted(false);
    h.initial.events.get('ended')?.();
    expect(h.microphone.track).toBeUndefined();
    expect(h.changed).toHaveBeenLastCalledWith({ muted: true, reason: 'device-ended' });
    expect(h.acquire).toHaveBeenCalledTimes(1);
  });
  it('coalesces duplicate enables while a permission prompt is pending', async () => {
    const waiting = deferred<LocalAudioTrack>();
    const h = setup(() => waiting.promise);
    h.microphone.connected();
    const first = h.microphone.setMuted(false);
    const second = h.microphone.setMuted(false);
    expect(h.acquire).toHaveBeenCalledTimes(1);
    waiting.resolve(h.initial.value);
    await Promise.all([first, second]);
    expect(h.local.publishTrack).toHaveBeenCalledTimes(1);
  });
  it('mute publication errors cannot keep hardware capturing', async () => {
    const h = setup();
    h.microphone.connected();
    await h.microphone.setMuted(false);
    h.local.unpublishTrack.mockRejectedValueOnce(new Error('signal lost'));
    await expect(h.microphone.setMuted(true)).rejects.toThrow('signal lost');
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.microphone.track).toBeUndefined();
    expect(h.changed).toHaveBeenLastCalledWith({ muted: true, reason: 'user' });
  });
});
