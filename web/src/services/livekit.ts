import {
  Room as LiveKitRoom,
  RoomEvent,
  createLocalAudioTrack,
  createAudioAnalyser,
} from 'livekit-client';
import type {
  RemoteParticipant,
  RemoteTrack,
  RemoteTrackPublication,
  LocalAudioTrack,
  RemoteAudioTrack,
} from 'livekit-client';
import type { Language, Membership } from '../types/domain';

export function shouldSubscribe(
  trackName: string,
  participantIdentity: string,
  selfId: string,
  language: Language,
  agentIdentity: string,
): boolean {
  if (participantIdentity !== agentIdentity) return false;
  const parts = trackName.split(':');
  return (
    parts.length === 3 && parts[0] === 'translated' && parts[1] !== selfId && parts[2] === language
  );
}
export interface AudioSession {
  setMuted: (value: boolean) => Promise<void>;
  setOutputMuted: (value: boolean) => void;
  setOutputDevice: (id: string) => Promise<void>;
  disconnect: () => Promise<void>;
  unlock: () => Promise<void>;
}
export async function connectAudio(
  m: Membership,
  input: string,
  output: string,
  initialMuted: boolean,
  onState: (state: string) => void,
  onLevel: (id: string, level: number) => void,
  signal?: AbortSignal,
): Promise<AudioSession> {
  if (!m.livekit) throw new Error('This room has no live audio credentials.');
  const lk = m.livekit;
  const room = new LiveKitRoom({ adaptiveStream: false, dynacast: false });
  const audios = new Map<string, HTMLMediaElement>();
  const analysers = new Map<
    string,
    { speaker: string; calculateVolume: () => number; cleanup: () => Promise<void> }
  >();
  let local: LocalAudioTrack | undefined;
  let closed = false;
  let outputMuted = false;
  let outputDevice = output;
  let timer: number | undefined;
  let microphoneGeneration = 0;
  const subscriptions = (publication: RemoteTrackPublication, participant: RemoteParticipant) =>
    publication.setSubscribed(
      shouldSubscribe(
        publication.trackName,
        participant.identity,
        m.participant.id,
        m.participant.language,
        lk.agent_identity,
      ),
    );
  const setSink = async (audio: HTMLMediaElement, id: string) => {
    if ('setSinkId' in audio)
      await (audio as HTMLAudioElement & { setSinkId: (value: string) => Promise<void> }).setSinkId(
        id,
      );
  };
  const cleanup = async () => {
    if (closed) return;
    closed = true;
    microphoneGeneration++;
    signal?.removeEventListener('abort', abort);
    clearInterval(timer);
    local?.stop();
    audios.forEach((el) => el.remove());
    audios.clear();
    await Promise.all([...analysers.values()].map((analyser) => analyser.cleanup()));
    analysers.clear();
    await room.disconnect();
  };
  const abort = () => {
    void cleanup();
  };
  signal?.addEventListener('abort', abort, { once: true });
  room.on(RoomEvent.TrackPublished, subscriptions);
  room.on(
    RoomEvent.TrackSubscribed,
    (track: RemoteTrack, publication: RemoteTrackPublication, participant: RemoteParticipant) => {
      if (
        !shouldSubscribe(
          publication.trackName,
          participant.identity,
          m.participant.id,
          m.participant.language,
          lk.agent_identity,
        )
      ) {
        publication.setSubscribed(false);
        return;
      }
      const audio = track.attach();
      audio.autoplay = true;
      audio.muted = outputMuted;
      audio.setAttribute('data-artha-audio', 'true');
      document.body.appendChild(audio);
      audios.set(publication.trackSid, audio);
      try {
        const analyser = createAudioAnalyser(track as RemoteAudioTrack);
        analysers.set(publication.trackSid, {
          ...analyser,
          speaker: publication.trackName.split(':')[1],
        });
      } catch {
        /* Speaker playback remains usable if Web Audio analysis is unavailable. */
      }
      void setSink(audio, outputDevice).catch(() =>
        onState('Audio connected. Use system settings to choose the speaker.'),
      );
      void audio.play().catch(() => onState('Click “Enable speaker” to allow playback.'));
    },
  );
  room.on(RoomEvent.TrackUnsubscribed, (track, publication) => {
    track.detach().forEach((el) => el.remove());
    audios.delete(publication.trackSid);
    const analyser = analysers.get(publication.trackSid);
    if (analyser) {
      onLevel(analyser.speaker, 0);
      void analyser.cleanup();
      analysers.delete(publication.trackSid);
    }
  });
  room.on(RoomEvent.Reconnecting, () => onState('Reconnecting audio…'));
  room.on(RoomEvent.Reconnected, () => onState('Audio connected'));
  room.on(RoomEvent.Disconnected, () =>
    onState(closed ? 'Disconnected' : 'Audio disconnected. Rejoin the room.'),
  );
  room.on(RoomEvent.ActiveSpeakersChanged, (speakers) =>
    speakers.forEach((p) => onLevel(p.identity, p.audioLevel)),
  );
  try {
    if (signal?.aborted) throw new Error('Audio connection cancelled.');
    await room.connect(lk.url, lk.token, { autoSubscribe: false });
    if (closed || signal?.aborted) {
      await room.disconnect();
      throw new Error('Audio connection cancelled.');
    }
    room.localParticipant.setTrackSubscriptionPermissions(false, [
      { participantIdentity: lk.agent_identity, allowAll: true },
    ]);
    room.remoteParticipants.forEach((p) =>
      p.trackPublications.forEach((pub) => subscriptions(pub, p)),
    );
    if (!initialMuted) {
      local = await createLocalAudioTrack({
        deviceId: input === 'default' ? undefined : input,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
      if (closed || signal?.aborted) {
        local.stop();
        throw new Error('Microphone request cancelled.');
      }
      await room.localParticipant.publishTrack(local, { name: `source:${m.participant.id}` });
    }
    onState('Audio connected');
    timer = window.setInterval(() => {
      onLevel(
        m.participant.id,
        local?.mediaStreamTrack.enabled ? room.localParticipant.audioLevel || 0 : 0,
      );
      analysers.forEach((analyser) => onLevel(analyser.speaker, analyser.calculateVolume()));
    }, 100);
  } catch (error) {
    await cleanup();
    throw error;
  }
  return {
    async setMuted(value) {
      if (closed) throw new Error('Audio connection is closed. Reconnect before unmuting.');
      const requestGeneration = ++microphoneGeneration;
      if (value) await local?.mute();
      else if (local) await local.unmute();
      else {
        const created = await createLocalAudioTrack({
          deviceId: input === 'default' ? undefined : input,
          echoCancellation: true,
          noiseSuppression: true,
        });
        if (closed || requestGeneration !== microphoneGeneration) {
          created.stop();
          return;
        }
        local = created;
        try {
          await room.localParticipant.publishTrack(local, { name: `source:${m.participant.id}` });
        } catch (error) {
          local.stop();
          local = undefined;
          throw error;
        }
      }
    },
    setOutputMuted(value) {
      outputMuted = value;
      audios.forEach((el) => {
        el.muted = value;
      });
    },
    async setOutputDevice(id) {
      outputDevice = id;
      await Promise.all([...audios.values()].map((el) => setSink(el, id)));
    },
    async unlock() {
      await room.startAudio();
      await Promise.all([...audios.values()].map((el) => el.play()));
    },
    disconnect: cleanup,
  };
}
