import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { captureMeetingCamera, captureMeetingMicrophone } from './localMediaCapture';
import { MeetingMicrophone } from './meetingMicrophoneCapture';
import { MeetingCamera } from './meetingVideo';
import type { Room } from 'livekit-client';

const sdk = vi.hoisted(() => ({ audio: vi.fn(), video: vi.fn(), restart: vi.fn() }));
vi.mock('livekit-client', () => {
  class OwnedTrack {
    source = '';
    isMuted = false;
    stop = vi.fn(() => this.mediaStreamTrack.stop());
    constructor(
      public mediaStreamTrack: MediaStreamTrack,
      public constraints: MediaTrackConstraints,
      public isUserProvided: boolean,
    ) {
      // Match the SDK's ended continuation: stopping alone does not mark mute.
      // Caller ownership prevents its fallback device acquisition.
      mediaStreamTrack.addEventListener('ended', async () => {
        await Promise.resolve();
        if (!this.isUserProvided && !this.isMuted) sdk.restart();
      });
    }
  }
  return {
    Track: { Source: { Microphone: 'microphone', Camera: 'camera' }, Kind: { Video: 'video' } },
    LocalAudioTrack: class extends OwnedTrack {
      constructor(raw: MediaStreamTrack, options: MediaTrackConstraints, owned: boolean) {
        super(raw, options, owned);
        sdk.audio(raw, options, owned);
      }
    },
    LocalVideoTrack: class extends OwnedTrack {
      constructor(raw: MediaStreamTrack, options: MediaTrackConstraints, owned: boolean) {
        super(raw, options, owned);
        sdk.video(raw, options, owned);
      }
    },
  };
});

function raw(kind: 'audio' | 'video') {
  const events = new EventTarget();
  return {
    kind,
    stop: vi.fn(),
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    end: () => events.dispatchEvent(new Event('ended')),
  };
}
const capture = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: capture } });
});
afterEach(() => vi.unstubAllGlobals());

describe('caller-owned meeting capture', () => {
  it('captures only the exact selected microphone with source and ownership explicit', async () => {
    const microphone = raw('audio');
    capture.mockResolvedValue({ getTracks: () => [microphone] });
    const constraints = { deviceId: { exact: 'chosen' }, echoCancellation: true };
    const track = await captureMeetingMicrophone(constraints);
    expect(capture).toHaveBeenCalledExactlyOnceWith({ audio: constraints, video: false });
    expect(sdk.audio).toHaveBeenCalledWith(microphone, constraints, true);
    expect(track.source).toBe('microphone');
  });
  it('captures only camera video with source and ownership explicit', async () => {
    const camera = raw('video');
    capture.mockResolvedValue({ getTracks: () => [camera] });
    const constraints = { width: 640, height: 360, frameRate: 24, facingMode: 'user' };
    const track = await captureMeetingCamera(constraints);
    expect(capture).toHaveBeenCalledExactlyOnceWith({ audio: false, video: constraints });
    expect(sdk.video).toHaveBeenCalledWith(camera, constraints, true);
    expect(track.source).toBe('camera');
  });
  it('never retries a failed exact device request on a different microphone', async () => {
    const error = Object.assign(new Error('device absent'), { name: 'OverconstrainedError' });
    capture.mockRejectedValueOnce(error);
    await expect(captureMeetingMicrophone({ deviceId: { exact: 'unplugged' } })).rejects.toBe(
      error,
    );
    expect(capture).toHaveBeenCalledTimes(1);
    expect(sdk.audio).not.toHaveBeenCalled();
  });
  it('stops every unexpected track when no requested track exists', async () => {
    const unexpected = raw('video');
    capture.mockResolvedValueOnce({ getTracks: () => [unexpected] });
    await expect(captureMeetingMicrophone({})).rejects.toThrow('No audio track');
    expect(unexpected.stop).toHaveBeenCalledOnce();
  });
  it('stops all captured hardware if wrapping fails', async () => {
    const requested = raw('audio');
    const unexpected = raw('video');
    capture.mockResolvedValueOnce({ getTracks: () => [requested, unexpected] });
    sdk.audio.mockImplementationOnce(() => {
      throw new Error('wrap failed');
    });
    await expect(captureMeetingMicrophone({})).rejects.toThrow('wrap failed');
    expect(requested.stop).toHaveBeenCalledOnce();
    expect(unexpected.stop).toHaveBeenCalledOnce();
  });
  it('stops unexpected tracks while preserving the requested capture', async () => {
    const requested = raw('audio');
    const unexpected = raw('video');
    capture.mockResolvedValueOnce({ getTracks: () => [requested, unexpected] });
    await captureMeetingMicrophone({});
    expect(requested.stop).not.toHaveBeenCalled();
    expect(unexpected.stop).toHaveBeenCalledOnce();
  });
  it('an ended microphone remains off after the SDK async device-loss continuation', async () => {
    const microphone = raw('audio');
    capture.mockResolvedValueOnce({ getTracks: () => [microphone] });
    const localParticipant = {
      publishTrack: vi.fn(async () => ({})),
      unpublishTrack: vi.fn(async () => {}),
    };
    const state = vi.fn();
    const meeting = new MeetingMicrophone(
      { localParticipant } as unknown as Room,
      'self',
      'default',
      state,
    );
    meeting.connected();
    await meeting.setMuted(false);
    expect(localParticipant.publishTrack).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ source: 'microphone', name: 'source:self' }),
    );
    microphone.end();
    await Promise.resolve();
    expect(state).toHaveBeenLastCalledWith({ muted: true, reason: 'device-ended' });
    expect(microphone.stop).toHaveBeenCalled();
    expect(sdk.restart).not.toHaveBeenCalled();
    expect(capture).toHaveBeenCalledTimes(1);
  });
  it('an ended camera remains off after the SDK async device-loss continuation', async () => {
    const camera = raw('video');
    capture.mockResolvedValueOnce({ getTracks: () => [camera] });
    const localParticipant = {
      publishTrack: vi.fn(async () => ({ trackSid: 'camera' })),
      unpublishTrack: vi.fn(async () => {}),
      setTrackSubscriptionPermissions: vi.fn(),
    };
    const state = vi.fn();
    const meeting = new MeetingCamera(
      { localParticipant, remoteParticipants: new Map() } as unknown as Room,
      'self',
      'agent',
      { track: vi.fn(), state },
    );
    await meeting.setEnabled(true);
    expect(localParticipant.publishTrack).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ source: 'camera', name: 'camera:self' }),
    );
    camera.end();
    await Promise.resolve();
    expect(state).toHaveBeenLastCalledWith({ enabled: false, pending: false, error: '' });
    expect(camera.stop).toHaveBeenCalled();
    expect(sdk.restart).not.toHaveBeenCalled();
    expect(capture).toHaveBeenCalledTimes(1);
  });
});
