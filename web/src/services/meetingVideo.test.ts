import { describe, expect, it, vi } from 'vitest';
import { Track } from 'livekit-client';
import type {
  LocalVideoTrack,
  RemoteTrackPublication,
  RemoteVideoTrack,
  Room,
} from 'livekit-client';
import {
  CAMERA_OFF,
  MeetingCamera,
  cameraPermissions,
  shouldSubscribeCamera,
} from './meetingVideo';
import type { CameraState, CameraTrack } from './meetingVideo';
import { CameraPreviewController } from './cameraPreview';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
function fakeTrack() {
  const events = new Map<string, () => void>();
  const raw = {
    stop: vi.fn(),
    mediaStreamTrack: {
      addEventListener: vi.fn((event: string, cb: () => void) => events.set(event, cb)),
      removeEventListener: vi.fn((event: string) => events.delete(event)),
    },
  };
  return { raw, events, track: raw as unknown as LocalVideoTrack };
}
function setup(capture?: () => Promise<LocalVideoTrack>) {
  const initial = fakeTrack();
  const callbacks = {
    track: vi.fn<(id: string, track: CameraTrack | null) => void>(),
    state: vi.fn<(state: CameraState) => void>(),
  };
  const local = {
    publishTrack: vi.fn(async () => ({ trackSid: 'camera-sid' })),
    unpublishTrack: vi.fn(async () => undefined),
    setTrackSubscriptionPermissions: vi.fn(),
  };
  const peers = new Map([
    ['agent', { identity: 'agent' }],
    ['other', { identity: 'other' }],
  ]);
  const room = { localParticipant: local, remoteParticipants: peers } as unknown as Pick<
    Room,
    'localParticipant' | 'remoteParticipants'
  >;
  const acquire = vi.fn(capture ?? (async () => initial.track));
  return {
    camera: new MeetingCamera(room, 'self', 'agent', callbacks, acquire),
    callbacks,
    local,
    peers,
    acquire,
    initial,
  };
}

describe('camera permissions preserve original-audio isolation', () => {
  it('allows camera video independently of the listener language, but never direct audio or agent video', () => {
    const publication = {
      kind: Track.Kind.Video,
      source: Track.Source.Camera,
      trackName: 'camera:other',
    };
    expect(
      shouldSubscribeCamera(publication as RemoteTrackPublication, 'other', 'self', 'agent'),
    ).toBe(true);
    for (const [change, owner] of [
      [{ kind: Track.Kind.Audio }, 'other'],
      [{ source: Track.Source.ScreenShare }, 'other'],
      [{ trackName: 'translated:other:ta' }, 'other'],
      [{}, 'self'],
      [{}, 'agent'],
      [{}, 'imposter'],
    ] as const)
      expect(
        shouldSubscribeCamera(
          { ...publication, ...change } as RemoteTrackPublication,
          owner,
          'self',
          'agent',
        ),
      ).toBe(false);
  });
  it('grants agent source access and peers only the camera SID, including late joins', async () => {
    const h = setup();
    h.camera.refreshPermissions();
    expect(h.local.setTrackSubscriptionPermissions).toHaveBeenLastCalledWith(false, [
      { participantIdentity: 'agent', allowAll: true },
      { participantIdentity: 'other', allowAll: false, allowedTrackSids: [] },
    ]);
    await h.camera.setEnabled(true);
    h.peers.set('late', { identity: 'late' });
    h.camera.refreshPermissions();
    expect(h.local.setTrackSubscriptionPermissions).toHaveBeenLastCalledWith(false, [
      { participantIdentity: 'agent', allowAll: true },
      { participantIdentity: 'other', allowAll: false, allowedTrackSids: ['camera-sid'] },
      { participantIdentity: 'late', allowAll: false, allowedTrackSids: ['camera-sid'] },
    ]);
    expect(cameraPermissions(['other', 'other', 'agent'], 'agent', 'camera-sid')).toHaveLength(2);
  });
});

describe('opt-in room camera lifecycle', () => {
  it('constructs without capture, then publishes a standard camera only after explicit enable', async () => {
    const h = setup();
    expect(h.acquire).not.toHaveBeenCalled();
    await h.camera.setEnabled(true);
    expect(h.acquire).toHaveBeenCalledTimes(1);
    expect(h.local.publishTrack).toHaveBeenCalledWith(
      h.initial.track,
      expect.objectContaining({ name: 'camera:self', source: Track.Source.Camera }),
    );
    expect(h.callbacks.track).toHaveBeenLastCalledWith('self', h.initial.track);
    expect(h.callbacks.state).toHaveBeenLastCalledWith({
      enabled: true,
      pending: false,
      error: '',
    });
  });
  it('turns off hardware and removes preview before waiting for unpublish acknowledgement', async () => {
    const h = setup();
    await h.camera.setEnabled(true);
    const waiting = deferred<undefined>();
    h.local.unpublishTrack.mockImplementation(() => waiting.promise);
    const stopped = h.camera.setEnabled(false);
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.callbacks.track).toHaveBeenLastCalledWith('self', null);
    expect(h.callbacks.state).toHaveBeenLastCalledWith(CAMERA_OFF);
    expect(h.local.setTrackSubscriptionPermissions).toHaveBeenLastCalledWith(
      false,
      expect.arrayContaining([
        { participantIdentity: 'other', allowAll: false, allowedTrackSids: [] },
      ]),
    );
    waiting.resolve(undefined);
    await stopped;
  });
  it('permission denial keeps sharing off and produces a useful retry message', async () => {
    const h = setup(async () => {
      throw { name: 'NotAllowedError' };
    });
    await expect(h.camera.setEnabled(true)).rejects.toThrow('Camera permission was denied');
    expect(h.local.publishTrack).not.toHaveBeenCalled();
    expect(h.callbacks.state).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        pending: false,
        error: expect.stringContaining('permission was denied'),
      }),
    );
  });
  it('publication failure stops the acquired camera and never announces an enabled preview', async () => {
    const h = setup();
    h.local.publishTrack.mockRejectedValueOnce(new Error('publish failed'));
    await expect(h.camera.setEnabled(true)).rejects.toThrow('could not start');
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.callbacks.state.mock.calls.some(([state]) => state.enabled)).toBe(false);
  });
  it('permission update failure during camera off cannot skip hardware release or unpublish', async () => {
    const h = setup();
    await h.camera.setEnabled(true);
    h.local.setTrackSubscriptionPermissions.mockImplementation(() => {
      throw new Error('signal lost');
    });
    await h.camera.setEnabled(false);
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.local.unpublishTrack).toHaveBeenCalledWith(h.initial.track);
    expect(h.callbacks.state).toHaveBeenLastCalledWith(CAMERA_OFF);
  });
  it('failed camera grant application never reports enabled capture', async () => {
    const h = setup();
    h.local.setTrackSubscriptionPermissions.mockImplementation(() => {
      throw new Error('signal lost');
    });
    await expect(h.camera.setEnabled(true)).rejects.toThrow('could not start');
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.callbacks.state.mock.calls.some(([state]) => state.enabled)).toBe(false);
    expect(h.callbacks.state).toHaveBeenLastCalledWith(
      expect.objectContaining({ enabled: false, error: expect.any(String) }),
    );
  });
  it('cancels a late permission result after off without publishing it', async () => {
    const waiting = deferred<LocalVideoTrack>();
    const h = setup(() => waiting.promise);
    const enabling = h.camera.setEnabled(true);
    await h.camera.setEnabled(false);
    waiting.resolve(h.initial.track);
    await enabling;
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.local.publishTrack).not.toHaveBeenCalled();
    expect(h.callbacks.state).toHaveBeenLastCalledWith(CAMERA_OFF);
  });
  it('does not duplicate capture while a permission prompt is pending', async () => {
    const waiting = deferred<LocalVideoTrack>();
    const h = setup(() => waiting.promise);
    const enabling = h.camera.setEnabled(true);
    await h.camera.setEnabled(true);
    expect(h.acquire).toHaveBeenCalledTimes(1);
    waiting.resolve(h.initial.track);
    await enabling;
  });
  it('disconnect prevents late camera activation and requires a new media session', async () => {
    const waiting = deferred<LocalVideoTrack>();
    const h = setup(() => waiting.promise);
    const enabling = h.camera.setEnabled(true);
    await h.camera.disconnect();
    waiting.resolve(h.initial.track);
    await enabling;
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.local.publishTrack).not.toHaveBeenCalled();
    await expect(h.camera.setEnabled(true)).rejects.toThrow('Reconnect media');
  });
  it('disconnect during publish stops hardware immediately and removes late publication', async () => {
    const h = setup();
    const published = deferred<{ trackSid: string }>();
    h.local.publishTrack.mockImplementation(() => published.promise);
    const enabling = h.camera.setEnabled(true);
    await Promise.resolve();
    await h.camera.disconnect();
    expect(h.initial.raw.stop).toHaveBeenCalled();
    published.resolve({ trackSid: 'late-camera' });
    await enabling;
    expect(h.local.unpublishTrack).toHaveBeenCalledWith(h.initial.track);
    expect(h.callbacks.state.mock.calls.some(([state]) => state.enabled)).toBe(false);
  });
  it('leaving does not wait for a lost camera-unpublish acknowledgement', async () => {
    const h = setup();
    await h.camera.setEnabled(true);
    const lost = deferred<undefined>();
    h.local.unpublishTrack.mockImplementation(() => lost.promise);
    await h.camera.disconnect();
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.callbacks.state).toHaveBeenLastCalledWith(CAMERA_OFF);
    lost.resolve(undefined);
  });
  it('off then on acquires a fresh camera track instead of unmuting a stopped device', async () => {
    const second = fakeTrack();
    const h = setup();
    h.acquire.mockResolvedValueOnce(h.initial.track).mockResolvedValueOnce(second.track);
    await h.camera.setEnabled(true);
    await h.camera.setEnabled(false);
    await h.camera.setEnabled(true);
    expect(h.acquire).toHaveBeenCalledTimes(2);
    expect(h.callbacks.track).toHaveBeenLastCalledWith('self', second.track);
  });
  it('updates peer grants when LiveKit republishes the camera after reconnect', async () => {
    const h = setup();
    await h.camera.setEnabled(true);
    h.camera.localPublished(h.initial.track, 'reconnected-camera');
    expect(h.local.setTrackSubscriptionPermissions).toHaveBeenLastCalledWith(
      false,
      expect.arrayContaining([
        { participantIdentity: 'other', allowAll: false, allowedTrackSids: ['reconnected-camera'] },
      ]),
    );
  });
  it('browser camera-ended event clears capture and sharing state', async () => {
    const h = setup();
    await h.camera.setEnabled(true);
    h.initial.events.get('ended')?.();
    await Promise.resolve();
    expect(h.initial.raw.stop).toHaveBeenCalled();
    expect(h.callbacks.state).toHaveBeenLastCalledWith(CAMERA_OFF);
  });
  it('an obsolete remote unsubscribe cannot remove a replacement camera track', () => {
    const h = setup();
    const old = {} as RemoteVideoTrack;
    const next = {} as RemoteVideoTrack;
    h.camera.remoteSubscribed(old, 'old-sid', 'other');
    h.camera.remoteSubscribed(next, 'new-sid', 'other');
    h.camera.remoteRemoved('old-sid', 'other');
    expect(h.callbacks.track).toHaveBeenLastCalledWith('other', next);
    h.camera.remoteRemoved('new-sid', 'other');
    expect(h.callbacks.track).toHaveBeenLastCalledWith('other', null);
  });
  it('leaving and disconnecting clears every remote camera without affecting audio', async () => {
    const h = setup();
    h.camera.remoteSubscribed({} as RemoteVideoTrack, 'sid', 'other');
    h.camera.participantLeft('other');
    expect(h.callbacks.track).toHaveBeenLastCalledWith('other', null);
    h.camera.remoteSubscribed({} as RemoteVideoTrack, 'late', 'other');
    await h.camera.disconnect();
    expect(h.callbacks.track).toHaveBeenLastCalledWith('other', null);
    expect(h.local.publishTrack).not.toHaveBeenCalled();
  });
});

function fakeStream() {
  const track = { stop: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() };
  const stream = {
    getTracks: () => [track],
    getVideoTracks: () => [track],
  } as unknown as MediaStream;
  return { track, stream };
}
describe('private prejoin camera preview', () => {
  it('requests video only after explicit start and stops it when leaving preview', async () => {
    const { track, stream } = fakeStream();
    const capture = vi.fn(async () => stream),
      changed = vi.fn();
    const preview = new CameraPreviewController(changed, capture);
    expect(capture).not.toHaveBeenCalled();
    await preview.start();
    expect(capture).toHaveBeenCalledWith(
      expect.objectContaining({ audio: false, video: expect.any(Object) }),
    );
    expect(changed).toHaveBeenLastCalledWith({ stream, pending: false, error: '' });
    preview.stop();
    expect(track.stop).toHaveBeenCalled();
    expect(changed).toHaveBeenLastCalledWith({ stream: null, pending: false, error: '' });
  });
  it('unmount cancels late permission results without emitting an active preview', async () => {
    const { track, stream } = fakeStream();
    const pending = deferred<MediaStream>(),
      changed = vi.fn();
    const preview = new CameraPreviewController(changed, () => pending.promise);
    const acquiring = preview.start();
    preview.close();
    pending.resolve(stream);
    await acquiring;
    expect(track.stop).toHaveBeenCalled();
    expect(changed.mock.calls.some(([state]) => state.stream)).toBe(false);
  });
  it('denied preview stays off and can be retried', async () => {
    const { stream } = fakeStream();
    const capture = vi
      .fn()
      .mockRejectedValueOnce({ name: 'NotAllowedError' })
      .mockResolvedValueOnce(stream);
    const changed = vi.fn();
    const preview = new CameraPreviewController(changed, capture);
    await preview.start();
    expect(changed).toHaveBeenLastCalledWith(
      expect.objectContaining({
        stream: null,
        pending: false,
        error: expect.stringContaining('permission was denied'),
      }),
    );
    await preview.start();
    expect(changed).toHaveBeenLastCalledWith({ stream, pending: false, error: '' });
  });
});
