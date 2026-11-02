import { Room as LiveKitRoom, RoomEvent, createAudioAnalyser, Track } from 'livekit-client';
import type {
  RemoteParticipant,
  RemoteTrack,
  RemoteTrackPublication,
  RemoteAudioTrack,
  RemoteVideoTrack,
} from 'livekit-client';
import type { Language, Membership } from '../types/domain';
import { transportChannel, transportMetrics } from './transportMetrics';
import type { MetricStat, TransportMetrics } from './transportMetrics';
import { request } from './api';
import { ProbeSignalTracker, isProbeChallenge, probeTrackForListener } from './audioProbe';
import type { ProbeChallenge, ProbeReport, ProbeSample } from './audioProbe';
import { MeetingCamera, shouldSubscribeCamera } from './meetingVideo';
import type { CameraEvents } from './meetingVideo';
import { MeetingMicrophone } from './meetingMicrophoneCapture';
import type { MicrophoneState } from './meetingMicrophoneCapture';
export type { MicrophoneState } from './meetingMicrophoneCapture';

export interface PlaybackState {
  status: 'ready' | 'blocked' | 'muted' | 'disconnected';
  error: string;
}
export interface AudioSessionEvents {
  microphone?: (state: MicrophoneState) => void;
  playback?: (state: PlaybackState) => void;
}

export function shouldSubscribe(
  trackName: string,
  participantIdentity: string,
  selfId: string,
  language: Language,
  agentIdentity: string,
  mode: Membership['room']['mode'] = 'live',
): boolean {
  if (participantIdentity !== agentIdentity) return false;
  if (mode !== 'demo' && probeTrackForListener(trackName, selfId)) return true;
  const parts = trackName.split(':');
  if (parts.length !== 3 || !parts[1] || parts[1] === selfId) return false;
  if (mode === 'transport') return parts[0] === 'raw' && parts[2] === 'all';
  return mode === 'live' && parts[0] === 'translated' && parts[2] === language;
}
export interface AudioSession {
  waveformSources: () => {
    microphone: MediaStreamTrack | null;
    received: MediaStreamTrack[];
    gain: number;
  };
  setLowerWhileSpeaking: (enabled: boolean) => void;
  setMuted: (value: boolean) => Promise<void>;
  setOutputMuted: (value: boolean) => void;
  setOutputDevice: (id: string) => Promise<void>;
  disconnect: () => Promise<void>;
  unlock: () => Promise<void>;
  probe: () => Promise<ProbeSample>;
  setCameraEnabled: (value: boolean) => Promise<void>;
}
export async function connectAudio(
  m: Membership,
  input: string,
  output: string,
  initialMuted: boolean,
  onState: (state: string) => void,
  onLevel: (id: string, level: number) => void,
  signal?: AbortSignal,
  cameraEvents: CameraEvents = { track: () => {}, state: () => {} },
  mediaEvents: AudioSessionEvents = {},
): Promise<AudioSession> {
  if (!m.livekit) throw new Error('This room has no live audio credentials.');
  const lk = m.livekit;
  const room = new LiveKitRoom({ adaptiveStream: false, dynacast: false });
  const camera = new MeetingCamera(room, m.participant.id, lk.agent_identity, cameraEvents);
  const audios = new Map<string, HTMLMediaElement>();
  const conversationOutputs = new Set<string>();
  let lowerWhileSpeaking = false;
  let restoreVolumeAt = 0;
  let conversationGain = 1;
  const applyConversationGain = (gain: number) => {
    if (gain === conversationGain) return;
    conversationGain = gain;
    for (const sid of conversationOutputs) {
      const output = audios.get(sid);
      if (output) output.volume = gain;
    }
  };
  const remoteAudio = new Map<string, RemoteAudioTrack>();
  const metricsChannel =
    typeof BroadcastChannel === 'undefined'
      ? null
      : new BroadcastChannel(transportChannel(m.room.code, m.participant.id));
  let lastMetrics: TransportMetrics | null = null;
  if (metricsChannel)
    metricsChannel.onmessage = ({ data }) => {
      if (data?.type === 'request' && lastMetrics) metricsChannel.postMessage(lastMetrics);
    };
  const analysers = new Map<
    string,
    {
      speaker: string;
      trackName: string;
      analyser: AnalyserNode;
      calculateVolume: () => number;
      cleanup: () => Promise<void>;
    }
  >();
  let closed = false;
  let connected = false;
  let cleanupPromise: Promise<void> | undefined;
  const microphone = new MeetingMicrophone(room, m.participant.id, input, (state) =>
    mediaEvents.microphone?.(state),
  );
  let outputMuted = false;
  let outputDevice = output;
  let timer: number | undefined;
  let statsTimer: number | undefined;
  let readingStats = false;
  let sinkQueue: Promise<void> = Promise.resolve();
  let outputGeneration = 0;
  let playSequence = 0;
  const playVersions = new WeakMap<HTMLMediaElement, number>();
  const blockedOutputs = new Set<string>();
  const playback = (status: PlaybackState['status'], error = '') =>
    mediaEvents.playback?.({
      status: !connected
        ? 'disconnected'
        : outputMuted && status !== 'disconnected'
          ? 'muted'
          : status === 'ready' && blockedOutputs.size
            ? 'blocked'
            : status,
      error,
    });
  let issuingProbe = false;
  let activeProbe: {
    tracker: ProbeSignalTracker;
    timer: number;
    resolve: (sample: ProbeSample) => void;
    reject: (error: Error) => void;
  } | null = null;
  const finishProbe = (report: ProbeReport) => {
    const pending = activeProbe;
    if (!pending) return;
    activeProbe = null;
    clearTimeout(pending.timer);
    void request<ProbeSample>(
      `/rooms/${m.room.code}/audio-probes/report`,
      {
        method: 'POST',
        body: JSON.stringify(report),
      },
      m.session_token,
    ).then(pending.resolve, pending.reject);
  };
  const subscriptions = (publication: RemoteTrackPublication, participant: RemoteParticipant) => {
    if (closed) return;
    publication.setSubscribed(
      shouldSubscribeCamera(
        publication,
        participant.identity,
        m.participant.id,
        lk.agent_identity,
      ) ||
        (publication.kind === Track.Kind.Audio &&
          shouldSubscribe(
            publication.trackName,
            participant.identity,
            m.participant.id,
            m.participant.language,
            lk.agent_identity,
            m.room.mode,
          )),
    );
  };
  const setSink = async (audio: HTMLMediaElement, id: string) => {
    if ('setSinkId' in audio)
      await (audio as HTMLAudioElement & { setSinkId: (value: string) => Promise<void> }).setSinkId(
        id,
      );
    else if (id !== 'default')
      throw new Error('This browser cannot choose a speaker. Use system audio settings.');
  };
  const stopElement = (audio: HTMLMediaElement) => {
    try {
      audio.pause();
    } catch {
      /* Continue releasing a failed element. */
    }
    audio.srcObject = null;
    audio.remove();
  };
  const removeAudio = (sid: string) => {
    const audio = audios.get(sid);
    const track = remoteAudio.get(sid);
    audios.delete(sid);
    conversationOutputs.delete(sid);
    remoteAudio.delete(sid);
    blockedOutputs.delete(sid);
    if (audio) playVersions.delete(audio);
    if (track) {
      try {
        track.detach().forEach(stopElement);
      } catch {
        /* The owned element is released below. */
      }
    }
    if (audio) stopElement(audio);
    const analyser = analysers.get(sid);
    analysers.delete(sid);
    if (analyser && !probeTrackForListener(analyser.trackName, m.participant.id))
      onLevel(analyser.speaker, 0);
    return analyser ? Promise.resolve().then(() => analyser.cleanup()) : Promise.resolve();
  };
  const configureAndPlay = (sid: string, audio: HTMLMediaElement) => {
    const version = ++playSequence;
    playVersions.set(audio, version);
    const current = () =>
      !closed && audios.get(sid) === audio && playVersions.get(audio) === version;
    const sink = sinkQueue.then(async () => {
      if (!current()) return;
      await setSink(audio, outputDevice);
    });
    sinkQueue = sink.catch(() => {});
    const operation = sink.then(async () => {
      if (!current()) return;
      await audio.play();
      if (current() && connected) {
        blockedOutputs.delete(sid);
        playback('ready');
      }
    });
    void operation.catch(() => {
      if (!current() || !connected) return;
      blockedOutputs.add(sid);
      playback('blocked', 'Enable speaker playback or choose another speaker device.');
      onState('Click “Enable speaker” to allow playback.');
    });
    return operation;
  };
  const cleanup = () => {
    if (cleanupPromise) return cleanupPromise;
    closed = true;
    connected = false;
    audios.forEach((audio) => playVersions.delete(audio));
    outputGeneration++;
    microphone.disconnect();
    playback('disconnected');
    const cancelled = activeProbe?.tracker.cancel();
    if (cancelled) finishProbe(cancelled);
    signal?.removeEventListener('abort', abort);
    clearInterval(timer);
    clearInterval(statsTimer);
    metricsChannel?.close();
    const cameraCleanup = camera.disconnect();
    const outputCleanup = [...audios.keys()].map(removeAudio);
    cleanupPromise = (async () => {
      await Promise.allSettled([...outputCleanup, cameraCleanup]);
      await room.disconnect();
    })();
    return cleanupPromise;
  };
  const abort = () => {
    void cleanup().catch(() => {});
  };
  const refreshPermissions = () => {
    if (closed) return false;
    try {
      camera.refreshPermissions();
      return true;
    } catch {
      void cleanup().catch(() => {});
      onState('Media permissions could not be applied. Rejoin the room.');
      return false;
    }
  };
  signal?.addEventListener('abort', abort, { once: true });
  room.on(RoomEvent.TrackPublished, subscriptions);
  room.on(RoomEvent.TrackSubscriptionPermissionChanged, (publication, permission, participant) => {
    // Camera grants arrive after publication, including for late joiners. Only
    // retry the same reviewed source/kind filter when the publisher allows it.
    if (permission === 'allowed') subscriptions(publication, participant);
  });
  room.on(
    RoomEvent.TrackSubscribed,
    (track: RemoteTrack, publication: RemoteTrackPublication, participant: RemoteParticipant) => {
      if (closed) {
        track.detach().forEach(stopElement);
        return;
      }
      if (
        shouldSubscribeCamera(
          publication,
          participant.identity,
          m.participant.id,
          lk.agent_identity,
        )
      ) {
        if (!publication.isMuted)
          camera.remoteSubscribed(
            track as RemoteVideoTrack,
            publication.trackSid,
            participant.identity,
          );
        return;
      }
      if (
        track.kind !== Track.Kind.Audio ||
        !shouldSubscribe(
          publication.trackName,
          participant.identity,
          m.participant.id,
          m.participant.language,
          lk.agent_identity,
          m.room.mode,
        )
      ) {
        publication.setSubscribed(false);
        return;
      }
      if (remoteAudio.has(publication.trackSid))
        void removeAudio(publication.trackSid).catch(() => {});
      const audio = track.attach();
      audio.autoplay = true;
      audio.muted = outputMuted;
      if (m.room.mode === 'live' && publication.trackName.startsWith('translated:')) {
        conversationOutputs.add(publication.trackSid);
        audio.volume = conversationGain;
      }
      audio.setAttribute('data-artha-audio', 'true');
      document.body.appendChild(audio);
      audios.set(publication.trackSid, audio);
      remoteAudio.set(publication.trackSid, track as RemoteAudioTrack);
      try {
        const analyser = createAudioAnalyser(track as RemoteAudioTrack);
        void (analyser.analyser.context as AudioContext).resume().catch(() => {
          /* A suspended analyser produces no receiver measurement. */
        });
        analysers.set(publication.trackSid, {
          ...analyser,
          speaker: publication.trackName.split(':')[1],
          trackName: publication.trackName,
        });
      } catch {
        /* Speaker playback remains usable if Web Audio analysis is unavailable. */
      }
      void configureAndPlay(publication.trackSid, audio).catch(() => {});
    },
  );
  room.on(RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
    if (track.kind === Track.Kind.Video) {
      camera.remoteRemoved(publication.trackSid, participant.identity);
      return;
    }
    if (remoteAudio.get(publication.trackSid) !== track) {
      track.detach().forEach(stopElement);
      return;
    }
    void removeAudio(publication.trackSid).catch(() => {});
  });
  room.on(RoomEvent.Reconnecting, () => {
    if (closed) return;
    connected = false;
    audios.forEach((audio) => playVersions.delete(audio));
    microphone.suspend('reconnecting');
    void camera.setEnabled(false).catch(() => {});
    playback('disconnected');
    onState('Reconnecting audio… Microphone and camera are off.');
  });
  room.on(RoomEvent.ParticipantConnected, refreshPermissions);
  room.on(RoomEvent.ParticipantDisconnected, (participant) =>
    camera.participantLeft(participant.identity),
  );
  room.on(RoomEvent.TrackUnpublished, (publication, participant) =>
    camera.remoteRemoved(publication.trackSid, participant.identity),
  );
  room.on(RoomEvent.TrackMuted, (publication, participant) => {
    if (publication.kind === Track.Kind.Video)
      camera.remoteRemoved(publication.trackSid, participant.identity);
  });
  room.on(RoomEvent.TrackUnmuted, (publication, participant) => {
    if (
      publication.track &&
      shouldSubscribeCamera(
        publication as RemoteTrackPublication,
        participant.identity,
        m.participant.id,
        lk.agent_identity,
      )
    )
      camera.remoteSubscribed(
        publication.track as RemoteVideoTrack,
        publication.trackSid,
        participant.identity,
      );
  });
  room.on(RoomEvent.LocalTrackPublished, (publication) => {
    try {
      camera.localPublished(publication.track, publication.trackSid);
    } catch {
      void cleanup().catch(() => {});
      onState('Media permissions could not be applied. Rejoin the room.');
    }
  });
  room.on(RoomEvent.LocalTrackUnpublished, (publication) => {
    camera.localUnpublished(publication.track);
    microphone.unpublished(publication.track);
  });
  room.on(RoomEvent.Reconnected, () => {
    if (closed) return;
    connected = true;
    microphone.connected();
    if (!refreshPermissions()) return;
    room.remoteParticipants.forEach((p) =>
      p.trackPublications.forEach((pub) => subscriptions(pub, p)),
    );
    audios.forEach((audio, sid) => void configureAndPlay(sid, audio).catch(() => {}));
    onState('Audio connected');
  });
  room.on(RoomEvent.Disconnected, () => {
    const intentional = closed;
    if (!closed) void cleanup().catch(() => {});
    onState(intentional ? 'Disconnected' : 'Audio disconnected. Rejoin the room.');
  });
  room.on(RoomEvent.AudioPlaybackStatusChanged, (playing) => {
    if (!closed) playback(playing ? 'ready' : 'blocked');
  });
  try {
    if (signal?.aborted) throw new Error('Audio connection cancelled.');
    await room.connect(lk.url, lk.token, { autoSubscribe: false });
    if (closed || signal?.aborted) {
      await room.disconnect();
      throw new Error('Audio connection cancelled.');
    }
    camera.refreshPermissions();
    connected = true;
    microphone.connected();
    room.remoteParticipants.forEach((p) =>
      p.trackPublications.forEach((pub) => subscriptions(pub, p)),
    );
    await microphone.setMuted(initialMuted, 'initial');
    if (closed || signal?.aborted) throw new Error('Audio connection cancelled.');
    playback(room.canPlaybackAudio ? 'ready' : 'blocked');
    onState('Audio connected');
    const reportStats = async () => {
      if (closed || readingStats) return;
      readingStats = true;
      try {
        const local = microphone.track;
        const tracks = [...remoteAudio.values(), ...(local ? [local] : [])];
        const reports = await Promise.allSettled(tracks.map((track) => track.getRTCStatsReport()));
        const rows: MetricStat[] = [];
        for (const report of reports) {
          if (report.status === 'fulfilled')
            report.value?.forEach((row) => rows.push(row as MetricStat));
        }
        if (!closed) {
          lastMetrics = transportMetrics(rows, remoteAudio.size);
          metricsChannel?.postMessage(lastMetrics);
        }
      } catch {
        // Optional diagnostics never affect media or permission decisions.
      } finally {
        readingStats = false;
      }
    };
    statsTimer = window.setInterval(() => void reportStats(), 5000);
    void reportStats();
    timer = window.setInterval(() => {
      if (closed) return;
      const local = microphone.track;
      const micOpen = !!local?.mediaStreamTrack.enabled;
      const micLevel = micOpen ? room.localParticipant.audioLevel || 0 : 0;
      onLevel(m.participant.id, micLevel);
      if (lowerWhileSpeaking) {
        const now = performance.now();
        if (micOpen && micLevel > 0.08) restoreVolumeAt = now + 350;
        applyConversationGain(micOpen && now < restoreVolumeAt ? 0.25 : 1);
      }
      analysers.forEach((analyser, sid) => {
        const volume = analyser.calculateVolume();
        if (probeTrackForListener(analyser.trackName, m.participant.id)) {
          const element = audios.get(sid);
          const playing =
            !!element &&
            !outputMuted &&
            !element.muted &&
            !element.paused &&
            analyser.analyser.context.state === 'running';
          const report = activeProbe?.tracker.observe(analyser.trackName, volume, playing);
          if (report) finishProbe(report);
        } else {
          const element = audios.get(sid);
          const playing =
            element &&
            !element.paused &&
            !element.muted &&
            !outputMuted &&
            analyser.analyser.context.state === 'running';
          onLevel(analyser.speaker, playing ? volume * element.volume : 0);
        }
      });
    }, 100);
  } catch (error) {
    await cleanup();
    throw error;
  }
  return {
    waveformSources() {
      const local = microphone.track?.mediaStreamTrack;
      const received: MediaStreamTrack[] = [];
      if (!closed && connected && !outputMuted) {
        for (const sid of conversationOutputs) {
          const element = audios.get(sid);
          const track = remoteAudio.get(sid)?.mediaStreamTrack;
          if (track && element && !element.muted && !element.paused && !blockedOutputs.has(sid))
            received.push(track);
        }
      }
      return {
        microphone: !closed && connected && local?.enabled ? local : null,
        received,
        gain: conversationGain,
      };
    },
    setLowerWhileSpeaking(enabled) {
      lowerWhileSpeaking = enabled && m.room.mode === 'live';
      if (!lowerWhileSpeaking) {
        restoreVolumeAt = 0;
        applyConversationGain(1);
      }
    },
    setCameraEnabled: (value) => {
      if (value && (closed || !connected))
        return Promise.reject(new Error('Reconnect audio before turning on your camera.'));
      return camera.setEnabled(value);
    },
    setMuted: (value) => microphone.setMuted(value),
    setOutputMuted(value) {
      if (closed) return;
      outputMuted = value;
      if (value) {
        const cancelled = activeProbe?.tracker.cancel();
        if (cancelled) finishProbe(cancelled);
      }
      audios.forEach((el) => {
        el.muted = value;
      });
      playback(value ? 'muted' : room.canPlaybackAudio ? 'ready' : 'blocked');
    },
    async setOutputDevice(id) {
      if (closed || !connected) throw new Error('Connect audio before changing the speaker.');
      const version = ++outputGeneration;
      outputDevice = id;
      const operation = sinkQueue.then(async () => {
        if (closed || version !== outputGeneration) return;
        await Promise.all([...audios.values()].map((el) => setSink(el, id)));
      });
      sinkQueue = operation.catch(() => {});
      await operation;
    },
    async unlock() {
      if (closed || !connected) throw new Error('Reconnect audio before enabling the speaker.');
      try {
        await room.startAudio();
        if (closed || !connected)
          throw new Error('Audio connection changed before playback started.');
        await Promise.allSettled(
          [...analysers.values()].map(({ analyser }) =>
            (analyser.context as AudioContext).resume(),
          ),
        );
        await Promise.all([...audios.entries()].map(([sid, el]) => configureAndPlay(sid, el)));
        if (!closed && connected) playback('ready');
      } catch (error) {
        if (!closed && connected)
          playback('blocked', 'Speaker playback could not start. Allow audio and try again.');
        throw error;
      }
    },
    async probe() {
      if (closed || !connected || outputMuted)
        throw new Error('Enable connected speaker output before running a receiver probe.');
      if (issuingProbe || activeProbe) throw new Error('A receiver probe is already running.');
      issuingProbe = true;
      try {
        await room.startAudio();
        const challenge = await request<ProbeChallenge>(
          `/rooms/${m.room.code}/audio-probes`,
          { method: 'POST' },
          m.session_token,
        );
        if (closed || outputMuted)
          throw new Error('Audio connection changed before the probe started.');
        if (!isProbeChallenge(challenge, m.participant.id))
          throw new Error('The receiver probe response was invalid.');
        return await new Promise<ProbeSample>((resolve, reject) => {
          const tracker = new ProbeSignalTracker(challenge);
          const timer = window.setTimeout(
            () => {
              const report = tracker.timeout();
              if (report) finishProbe(report);
            },
            Math.max(100, challenge.expires_in_ms - 1000),
          );
          activeProbe = { tracker, timer, resolve, reject };
          tracker.start();
          void request(
            `/rooms/${m.room.code}/audio-probes/${challenge.probe_id}/start`,
            { method: 'POST' },
            m.session_token,
          ).catch((error) => {
            if (activeProbe?.tracker !== tracker) return;
            clearTimeout(timer);
            activeProbe = null;
            reject(error);
          });
        });
      } finally {
        issuingProbe = false;
      }
    },
    disconnect: cleanup,
  };
}
