import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RoomEvent, Track } from 'livekit-client';
import { connectAudio } from './livekit';
import type { AudioSession, AudioSessionEvents } from './livekit';
import type { Membership } from '../types/domain';

const sdk = vi.hoisted(() => ({ rooms: [] as any[], capture: vi.fn(), analyser: vi.fn() }));
vi.mock('./localMediaCapture', () => ({
  captureMeetingMicrophone: (...args: unknown[]) => sdk.capture(...args),
  captureMeetingCamera: vi.fn(() => {
    throw new Error('Unexpected camera capture');
  }),
}));
vi.mock('livekit-client', () => ({
  Track: {
    Kind: { Audio: 'audio', Video: 'video' },
    Source: { Microphone: 'microphone', Camera: 'camera' },
  },
  RoomEvent: Object.fromEntries(
    [
      'TrackPublished',
      'TrackSubscriptionPermissionChanged',
      'TrackSubscribed',
      'TrackUnsubscribed',
      'Reconnecting',
      'Reconnected',
      'Disconnected',
      'ParticipantConnected',
      'ParticipantDisconnected',
      'TrackUnpublished',
      'TrackMuted',
      'TrackUnmuted',
      'LocalTrackPublished',
      'LocalTrackUnpublished',
      'ActiveSpeakersChanged',
      'AudioPlaybackStatusChanged',
    ].map((value) => [value, value]),
  ),
  createLocalAudioTrack: (...args: unknown[]) => sdk.capture(...args),
  createLocalVideoTrack: vi.fn(() => {
    throw new Error('Unexpected camera capture');
  }),
  createAudioAnalyser: (...args: unknown[]) => sdk.analyser(...args),
  Room: class {
    handlers = new Map<string, Array<(...args: any[]) => void>>();
    remoteParticipants = new Map();
    canPlaybackAudio = false;
    localParticipant = {
      audioLevel: 0,
      publishTrack: vi.fn(async () => ({ trackSid: 'local-sid' })),
      unpublishTrack: vi.fn(async () => undefined),
      setTrackSubscriptionPermissions: vi.fn(),
    };
    connect = vi.fn(async () => undefined);
    disconnect = vi.fn(async () => undefined);
    startAudio = vi.fn(async () => {
      this.canPlaybackAudio = true;
      this.emit('AudioPlaybackStatusChanged', true);
    });
    constructor() {
      sdk.rooms.push(this);
    }
    on(name: string, callback: (...args: any[]) => void) {
      this.handlers.set(name, [...(this.handlers.get(name) ?? []), callback]);
      return this;
    }
    emit(name: string, ...args: any[]) {
      this.handlers.get(name)?.forEach((callback) => callback(...args));
    }
  },
}));

const membership = {
  room: { code: 'local-room', mode: 'live' },
  participant: { id: 'self', language: 'ta', muted: true },
  session_token: 'fixture-token',
  livekit: { url: 'ws://fixture', token: 'fixture', agent_identity: 'agent' },
} as Membership;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
async function flush() {
  for (let count = 0; count < 20; count++) await Promise.resolve();
}
function microphoneTrack() {
  return {
    stop: vi.fn(),
    mediaStreamTrack: { enabled: true, addEventListener: vi.fn(), removeEventListener: vi.fn() },
    getRTCStatsReport: vi.fn(async () => new Map()),
  };
}
function remoteAudio(sid = 'remote-sid') {
  const element: any = {
    autoplay: false,
    muted: false,
    volume: 1,
    paused: true,
    srcObject: {},
    setAttribute: vi.fn(),
    play: vi.fn(async () => {
      element.paused = false;
    }),
    pause: vi.fn(() => {
      element.paused = true;
    }),
    remove: vi.fn(),
    setSinkId: vi.fn(async () => undefined),
  };
  const track = {
    kind: Track.Kind.Audio,
    mediaStreamTrack: { id: sid, enabled: true, readyState: 'live' },
    attach: vi.fn(() => element),
    detach: vi.fn(() => [element]),
    getRTCStatsReport: vi.fn(async () => new Map()),
  };
  const publication = {
    trackSid: sid,
    trackName: 'translated:other:ta',
    kind: Track.Kind.Audio,
    source: Track.Source.Microphone,
    setSubscribed: vi.fn(),
  };
  return { element, track, publication, participant: { identity: 'agent' } };
}
const sessions: AudioSession[] = [];
async function connect(events: AudioSessionEvents = {}) {
  const states = vi.fn();
  const session = await connectAudio(
    membership,
    'default',
    'default',
    true,
    states,
    vi.fn(),
    undefined,
    undefined,
    events,
  );
  sessions.push(session);
  return { session, room: sdk.rooms.at(-1), states };
}

beforeEach(() => {
  sdk.rooms.length = 0;
  sdk.capture.mockReset();
  sdk.capture.mockResolvedValue(microphoneTrack());
  sdk.analyser.mockReset();
  sdk.analyser.mockImplementation(() => {
    throw new Error('Analysis unavailable');
  });
  vi.stubGlobal('BroadcastChannel', undefined);
  vi.stubGlobal('window', { setInterval: vi.fn(() => 1001), setTimeout });
  vi.stubGlobal('document', { body: { appendChild: vi.fn() } });
});
afterEach(async () => {
  await Promise.allSettled(sessions.splice(0).map((session) => session.disconnect()));
  vi.unstubAllGlobals();
});

describe('room media lifecycle with SDK doubles', () => {
  it('lowers only routed conversation playback during local speech and restores it without unmuting output', async () => {
    const { session, room } = await connect();
    const conversation = remoteAudio();
    const probe = remoteAudio('probe-sid');
    probe.publication.trackName = 'probe:' + 'a'.repeat(32) + ':self';
    room.emit(
      RoomEvent.TrackSubscribed,
      conversation.track,
      conversation.publication,
      conversation.participant,
    );
    room.emit(RoomEvent.TrackSubscribed, probe.track, probe.publication, probe.participant);
    await session.setMuted(false);
    await flush();
    const tick = vi
      .mocked(window.setInterval)
      .mock.calls.find(([, interval]) => interval === 100)![0] as () => void;
    room.localParticipant.audioLevel = 0.5;
    let clockMs = 2000;
    vi.stubGlobal('performance', { now: () => clockMs });
    tick();
    expect(conversation.element.volume).toBe(1);
    session.setLowerWhileSpeaking(true);
    tick();
    expect(conversation.element.volume).toBe(0.25);
    expect(probe.element.volume).toBe(1);
    expect(session.waveformSources().microphone).toBeTruthy();
    expect(session.waveformSources().received).toEqual([conversation.track.mediaStreamTrack]);
    room.localParticipant.audioLevel = 0;
    clockMs += 125;
    tick();
    expect(conversation.element.volume).toBe(0.25);
    clockMs += 230;
    tick();
    expect(conversation.element.volume).toBe(1);
    session.setOutputMuted(true);
    expect(session.waveformSources().received).toEqual([]);
    await session.setMuted(true);
    tick();
    expect(conversation.element.volume).toBe(1);
    expect(conversation.element.muted).toBe(true);
    expect(session.waveformSources().microphone).toBeNull();
  });
  it('joins muted, permits explicit microphone capture and stops it on reconnect', async () => {
    const events = { microphone: vi.fn(), playback: vi.fn() };
    const { session, room } = await connect(events);
    expect(sdk.capture).not.toHaveBeenCalled();
    await session.setMuted(false);
    const local = sdk.capture.mock.results[0].value;
    const captured = await local;
    room.emit(RoomEvent.Reconnecting);
    expect(captured.stop).toHaveBeenCalled();
    expect(events.microphone).toHaveBeenLastCalledWith({ muted: true, reason: 'reconnecting' });
    await expect(session.setMuted(false)).rejects.toThrow('not connected');
    await expect(session.setCameraEnabled(true)).rejects.toThrow('Reconnect');
    room.emit(RoomEvent.Reconnected);
    expect(sdk.capture).toHaveBeenCalledTimes(1);
    await session.setMuted(false);
    expect(sdk.capture).toHaveBeenCalledTimes(2);
  });
  it('unsubscribes direct source audio without ever attaching a speaker element', async () => {
    const { room } = await connect();
    const remote = remoteAudio();
    remote.publication.trackName = 'source:other';
    room.emit(RoomEvent.TrackSubscribed, remote.track, remote.publication, { identity: 'other' });
    expect(remote.track.attach).not.toHaveBeenCalled();
    expect(remote.publication.setSubscribed).toHaveBeenCalledWith(false);
  });
  it('late autoplay rejection cannot change state after a track is removed', async () => {
    const playback = vi.fn();
    const { room } = await connect({ playback });
    const remote = remoteAudio();
    const playing = deferred<void>();
    remote.element.play.mockImplementation(() => playing.promise);
    room.emit(RoomEvent.TrackSubscribed, remote.track, remote.publication, remote.participant);
    await flush();
    expect(remote.element.play).toHaveBeenCalled();
    room.emit(RoomEvent.TrackUnsubscribed, remote.track, remote.publication, remote.participant);
    const count = playback.mock.calls.length;
    playing.reject(new Error('Autoplay denied'));
    await flush();
    expect(playback).toHaveBeenCalledTimes(count);
    expect(remote.element.pause).toHaveBeenCalled();
    expect(remote.element.srcObject).toBeNull();
  });
  it('late autoplay rejection across reconnect cannot override restored playback', async () => {
    const playback = vi.fn();
    const { room } = await connect({ playback });
    const remote = remoteAudio();
    const oldPlay = deferred<void>();
    remote.element.play.mockImplementationOnce(() => oldPlay.promise);
    room.emit(RoomEvent.TrackSubscribed, remote.track, remote.publication, remote.participant);
    await flush();
    room.emit(RoomEvent.Reconnecting);
    expect(playback).toHaveBeenLastCalledWith({ status: 'disconnected', error: '' });
    room.emit(RoomEvent.Reconnected);
    await flush();
    expect(playback).toHaveBeenLastCalledWith({ status: 'ready', error: '' });
    const count = playback.mock.calls.length;
    oldPlay.reject(new Error('old interrupted playback'));
    await flush();
    expect(playback).toHaveBeenCalledTimes(count);
  });
  it('stale SDK playback state stays disconnected until reconnection succeeds', async () => {
    const playback = vi.fn();
    const { room, session } = await connect({ playback });
    room.emit(RoomEvent.Reconnecting);
    room.emit(RoomEvent.AudioPlaybackStatusChanged, true);
    expect(playback).toHaveBeenLastCalledWith({ status: 'disconnected', error: '' });
    session.setOutputMuted(false);
    expect(playback).toHaveBeenLastCalledWith({ status: 'disconnected', error: '' });
  });
  it('autoplay errors use a structured blocked state and explicit unlock clears it', async () => {
    const playback = vi.fn();
    const { room, session } = await connect({ playback });
    const remote = remoteAudio();
    remote.element.play.mockRejectedValueOnce(new Error('Autoplay denied'));
    room.emit(RoomEvent.TrackSubscribed, remote.track, remote.publication, remote.participant);
    await flush();
    expect(playback).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'blocked' }));
    await session.unlock();
    expect(playback).toHaveBeenLastCalledWith({ status: 'ready', error: '' });
    session.setOutputMuted(true);
    expect(playback).toHaveBeenLastCalledWith({ status: 'muted', error: '' });
  });
  it('analyser cleanup rejection still pauses, detaches and disconnects the room', async () => {
    sdk.analyser.mockReturnValue({
      analyser: { context: { resume: async () => undefined } },
      calculateVolume: () => 0,
      cleanup: vi.fn(async () => {
        throw new Error('Context already closed');
      }),
    });
    const { room, session } = await connect();
    const remote = remoteAudio();
    room.emit(RoomEvent.TrackSubscribed, remote.track, remote.publication, remote.participant);
    await flush();
    await session.disconnect();
    expect(remote.track.detach).toHaveBeenCalled();
    expect(remote.element.pause).toHaveBeenCalled();
    expect(remote.element.srcObject).toBeNull();
    expect(room.disconnect).toHaveBeenCalledTimes(1);
    await session.disconnect();
    expect(room.disconnect).toHaveBeenCalledTimes(1);
  });
  it('unexpected room disconnect releases active capture and makes old session unusable', async () => {
    const events = { microphone: vi.fn(), playback: vi.fn() };
    const { room, session, states } = await connect(events);
    await session.setMuted(false);
    const local = await sdk.capture.mock.results[0].value;
    room.emit(RoomEvent.Disconnected);
    await flush();
    expect(local.stop).toHaveBeenCalled();
    expect(events.playback).toHaveBeenLastCalledWith({ status: 'disconnected', error: '' });
    expect(states).toHaveBeenLastCalledWith('Audio disconnected. Rejoin the room.');
    await expect(session.setMuted(false)).rejects.toThrow('not connected');
    await expect(session.unlock()).rejects.toThrow('Reconnect');
  });
  it('speaker device operations finish in order, so an old request cannot overwrite the latest', async () => {
    const { room, session } = await connect();
    const remote = remoteAudio();
    room.emit(RoomEvent.TrackSubscribed, remote.track, remote.publication, remote.participant);
    await flush();
    const old = deferred<void>();
    remote.element.setSinkId.mockImplementation((id: string) =>
      id === 'old' ? old.promise : Promise.resolve(),
    );
    const first = session.setOutputDevice('old');
    await flush();
    const second = session.setOutputDevice('new');
    expect(remote.element.setSinkId).not.toHaveBeenCalledWith('new');
    old.resolve(undefined);
    await Promise.all([first, second]);
    expect(remote.element.setSinkId).toHaveBeenLastCalledWith('new');
  });
  it('a stale unsubscribe cannot remove a replacement track with the same publication SID', async () => {
    const { room } = await connect();
    const old = remoteAudio();
    const next = remoteAudio();
    room.emit(RoomEvent.TrackSubscribed, old.track, old.publication, old.participant);
    await flush();
    room.emit(RoomEvent.TrackSubscribed, next.track, next.publication, next.participant);
    await flush();
    room.emit(RoomEvent.TrackUnsubscribed, old.track, old.publication, old.participant);
    expect(next.element.pause).not.toHaveBeenCalled();
    expect(next.track.detach).not.toHaveBeenCalled();
  });
  it('a pending play promise does not block changing the output device', async () => {
    const { room, session } = await connect();
    const remote = remoteAudio();
    const playing = deferred<void>();
    remote.element.play.mockImplementation(() => playing.promise);
    room.emit(RoomEvent.TrackSubscribed, remote.track, remote.publication, remote.participant);
    await flush();
    await session.setOutputDevice('new-output');
    expect(remote.element.setSinkId).toHaveBeenLastCalledWith('new-output');
    playing.resolve(undefined);
    await flush();
  });
  it('one successfully playing route does not hide another blocked route', async () => {
    const playback = vi.fn();
    const { room } = await connect({ playback });
    const blocked = remoteAudio('blocked');
    blocked.element.play.mockRejectedValue(new Error('Not allowed'));
    room.emit(RoomEvent.TrackSubscribed, blocked.track, blocked.publication, blocked.participant);
    await flush();
    const ready = remoteAudio('ready');
    room.emit(RoomEvent.TrackSubscribed, ready.track, ready.publication, ready.participant);
    await flush();
    expect(playback).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'blocked' }));
  });
  it('unsafe permission-update errors close media instead of retaining active capture', async () => {
    const { room, session } = await connect();
    await session.setMuted(false);
    const local = await sdk.capture.mock.results[0].value;
    room.localParticipant.setTrackSubscriptionPermissions.mockImplementation(() => {
      throw new Error('signal unavailable');
    });
    room.emit(RoomEvent.ParticipantConnected, { identity: 'late-peer' });
    await flush();
    expect(local.stop).toHaveBeenCalled();
    expect(room.disconnect).toHaveBeenCalledTimes(1);
  });
});
