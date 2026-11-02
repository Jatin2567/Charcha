import { useEffect, useRef, useState } from 'react';
import type { Membership, Participant } from '../types/domain';
import type { AudioSession, PlaybackState, MicrophoneState } from '../services/livekit';
import { useApp } from '../state/AppContext';
import { useConferenceReadiness } from './useConferenceReadiness';
import { setConferenceMuted } from '../services/conferenceReadiness';
import { changeMeetingMicrophone, MeetingMuteBarrier } from '../services/meetingMicrophone';
import type { ProbeSample } from '../services/audioProbe';
import { CAMERA_OFF } from '../services/cameraState';
import type { CameraState } from '../services/cameraState';
import type { CameraTrack } from '../services/meetingVideo';

export function useMeetingAudio(m: Membership) {
  const app = useApp();
  const readiness = useConferenceReadiness(m);
  const latest = useRef(m);
  latest.current = m;
  const session = useRef<AudioSession | null>(null);
  const demo = m.room.mode === 'demo';
  const [muted, setMuted] = useState(true);
  const [outputMuted, setOutputMuted] = useState(false);
  const [lowerWhileSpeaking, setLowerWhileSpeaking] = useState(false);
  const lowerRef = useRef(false);
  const [mediaReady, setMediaReady] = useState(false);
  const [status, setStatus] = useState(
    demo ? 'Scripted demo · microphone is not transmitted' : 'Connecting audio…',
  );
  const [error, setError] = useState('');
  const [playback, setPlayback] = useState<PlaybackState>({ status: 'disconnected', error: '' });
  const [unlocking, setUnlocking] = useState(false);
  const [level, setLevel] = useState(0);
  const [levels, setLevels] = useState<Record<string, number>>({});
  const [camera, setCamera] = useState<CameraState>({ ...CAMERA_OFF });
  const [videoTracks, setVideoTracks] = useState<Record<string, CameraTrack>>({});
  const cameraRef = useRef(camera);
  cameraRef.current = camera;
  const [working, setWorking] = useState(false);
  const [probeWorking, setProbeWorking] = useState(false);
  const [probeResult, setProbeResult] = useState<ProbeSample | null>(null);
  const [retry, setRetry] = useState(0);
  const mutedRef = useRef(true);
  const pending = useRef(false);
  const unlockPending = useRef(false);
  const generation = useRef(0);
  const muteBarrier = useRef<MeetingMuteBarrier | null>(null);
  if (!muteBarrier.current)
    muteBarrier.current = new MeetingMuteBarrier((membership) =>
      setConferenceMuted(membership, true),
    );
  const outputRef = useRef(false);
  outputRef.current = outputMuted;
  mutedRef.current = muted;

  const requestServerMute = (membership: Membership) => {
    return muteBarrier.current!.mute(membership);
  };

  const rememberMuted = (value: boolean, participant?: Participant) => {
    mutedRef.current = value;
    setMuted(value);
    const current = latest.current;
    app.setMembership({
      ...current,
      participant: { ...current.participant, ...participant, muted: value },
    });
  };

  useEffect(() => {
    const version = ++generation.current;
    let disposed = false;
    const controller = new AbortController();
    setCamera({ ...CAMERA_OFF });
    setVideoTracks({});
    setLevel(0);
    setLevels({});
    setMediaReady(false);
    setMuted(true);
    mutedRef.current = true;
    setPlayback({ status: 'disconnected', error: '' });
    setStatus(demo ? 'Scripted demo · microphone is not transmitted' : 'Connecting audio…');
    if (demo) return;
    if (!m.livekit) {
      setStatus('Live audio unavailable. Rejoin this conversation.');
      return;
    }
    const current = () => !disposed && version === generation.current;
    const synchronizeMuted = () => {
      if (!current()) return;
      rememberMuted(true);
      void requestServerMute(latest.current).catch(() => {
        /* Readiness exposes stale membership separately. */
      });
    };
    const microphoneEvent = (event: MicrophoneState) => {
      if (!current()) return;
      setMuted(event.muted);
      mutedRef.current = event.muted;
      if (event.reason === 'reconnecting' || event.reason === 'disconnected') setMediaReady(false);
      if (['reconnecting', 'disconnected', 'device-ended', 'error'].includes(event.reason))
        synchronizeMuted();
      if (event.reason === 'device-ended')
        setError('The microphone was disconnected. Select a microphone, then unmute when ready.');
    };
    // Reloaded tabs, input changes and reconnects never inherit permission to capture.
    void requestServerMute(m)
      .then(() => import('../services/livekit'))
      .then(({ connectAudio }) => {
        if (!current()) throw new Error('Audio connection cancelled.');
        rememberMuted(true);
        return connectAudio(
          m,
          app.preferences.inputDevice,
          app.preferences.outputDevice,
          true,
          (next) => {
            if (current()) {
              setStatus(next);
              if (next.startsWith('Audio connected')) setMediaReady(true);
            }
          },
          (id, value) => {
            if (current()) {
              if (id === m.participant.id) setLevel(value);
              setLevels((levels) => ({ ...levels, [id]: value }));
            }
          },
          controller.signal,
          {
            track: (id, track) => {
              if (current())
                setVideoTracks((tracks) => {
                  const next = { ...tracks };
                  if (track) next[id] = track;
                  else delete next[id];
                  return next;
                });
            },
            state: (next) => {
              if (current()) setCamera(next);
            },
          },
          {
            microphone: microphoneEvent,
            playback: (next) => {
              if (current()) setPlayback(next);
            },
          },
        );
      })
      .then((connected) => {
        if (!current()) void connected.disconnect();
        else {
          session.current = connected;
          connected.setLowerWhileSpeaking(lowerRef.current);
          connected.setOutputMuted(outputRef.current);
          setMediaReady(true);
        }
      })
      .catch((issue) => {
        if (current()) {
          setMediaReady(false);
          setStatus('Audio unavailable');
          setError(
            issue instanceof Error
              ? issue.message
              : 'Audio could not connect. Rejoin or reconnect the room.',
          );
        }
      });
    return () => {
      disposed = true;
      generation.current++;
      controller.abort();
      const old = session.current;
      session.current = null;
      void old?.disconnect();
    };
  }, [
    m.participant.id,
    m.participant.language,
    m.session_token,
    m.room.code,
    m.room.mode,
    demo,
    app.preferences.inputDevice,
    retry,
  ]);

  useEffect(() => {
    const current = session.current;
    if (current)
      void current
        .setOutputDevice(app.preferences.outputDevice)
        .catch(() =>
          setError(
            'The selected speaker is unavailable. Choose another device or the system default.',
          ),
        );
  }, [app.preferences.outputDevice]);

  const toggleMic = async () => {
    if (pending.current || demo) return;
    pending.current = true;
    setWorking(true);
    setError('');
    const next = !mutedRef.current;
    const version = generation.current,
      current = session.current;
    const membership = latest.current;
    try {
      if (!current) {
        if (!next) throw new Error('Audio is not connected. Reconnect before unmuting.');
        rememberMuted(true);
        await requestServerMute(membership);
        return;
      }
      const participant = await changeMeetingMicrophone({
        muted: next,
        media: current,
        readiness: async () => {
          await muteBarrier.current!.wait(membership);
          return readiness.refresh();
        },
        update: (value) =>
          value ? requestServerMute(membership) : setConferenceMuted(membership, false),
        isCurrent: () => version === generation.current && session.current === current,
      });
      if (version === generation.current) rememberMuted(next, participant);
    } catch (issue) {
      if (version === generation.current) {
        rememberMuted(true);
        setError(issue instanceof Error ? issue.message : 'The microphone could not change state.');
      }
    } finally {
      pending.current = false;
      setWorking(false);
    }
  };
  const unlock = async () => {
    if (unlockPending.current) return;
    const current = session.current,
      version = generation.current;
    if (!current) {
      setError('Connect audio before enabling the speaker.');
      return;
    }
    unlockPending.current = true;
    setUnlocking(true);
    setError('');
    try {
      current.setOutputMuted(false);
      outputRef.current = false;
      setOutputMuted(false);
      await current.unlock();
    } catch (issue) {
      if (version === generation.current)
        setError(
          issue instanceof Error
            ? issue.message
            : 'Speaker playback is blocked. Allow audio for this site.',
        );
    } finally {
      unlockPending.current = false;
      setUnlocking(false);
    }
  };
  const toggleOutput = async () => {
    if (!session.current) return;
    if (playback.status === 'blocked' || outputRef.current) {
      await unlock();
      return;
    }
    session.current.setOutputMuted(true);
    outputRef.current = true;
    setOutputMuted(true);
  };
  return {
    waveformSession: session,
    lowerWhileSpeaking,
    changeLowerWhileSpeaking: (enabled: boolean) => {
      lowerRef.current = enabled;
      setLowerWhileSpeaking(enabled);
      session.current?.setLowerWhileSpeaking(enabled);
    },
    muted,
    outputMuted,
    mediaReady,
    playback,
    unlocking,
    status,
    error,
    level,
    levels,
    camera,
    videoTracks,
    readiness,
    canUnmute: mediaReady && !readiness.stale && readiness.report?.microphone.can_unmute === true,
    toggleCamera: async () => {
      if (demo || cameraRef.current.pending) return;
      const current = session.current,
        version = generation.current;
      if (!current || !mediaReady || (readiness.stale && !cameraRef.current.enabled)) {
        setCamera({ ...CAMERA_OFF, error: 'Connect to the room before turning on your camera.' });
        return;
      }
      try {
        await current.setCameraEnabled(!cameraRef.current.enabled);
      } catch (issue) {
        if (version === generation.current)
          setCamera({
            ...CAMERA_OFF,
            error: issue instanceof Error ? issue.message : 'Camera could not start.',
          });
      }
    },
    working,
    toggleMic,
    toggleOutput,
    probeWorking,
    probeResult,
    probe: async () => {
      if (!session.current || probeWorking) return;
      setProbeWorking(true);
      setError('');
      setProbeResult(null);
      const version = generation.current;
      try {
        const sample = await session.current.probe();
        if (version === generation.current) setProbeResult(sample);
      } catch (issue) {
        if (version === generation.current)
          setError(issue instanceof Error ? issue.message : 'Receiver check failed.');
      } finally {
        setProbeWorking(false);
      }
    },
    clearError: () => {
      setError('');
      setCamera((current) => ({ ...current, error: '' }));
    },
    unlock,
    disconnect: async () => {
      generation.current++;
      const current = session.current;
      session.current = null;
      setMediaReady(false);
      setMuted(true);
      mutedRef.current = true;
      await current?.disconnect();
    },
    retry: () => {
      generation.current++;
      const current = session.current;
      session.current = null;
      void current?.disconnect();
      rememberMuted(true);
      void requestServerMute(latest.current).catch(() => {});
      setMediaReady(false);
      setError('');
      setStatus('Reconnecting audio…');
      setRetry((value) => value + 1);
    },
  };
}
