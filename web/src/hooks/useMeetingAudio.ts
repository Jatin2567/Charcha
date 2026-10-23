import { useEffect, useRef, useState } from 'react';
import type { Membership, Participant } from '../types/domain';
import type { AudioSession } from '../services/livekit';
import { useApp } from '../state/AppContext';
import { updateParticipant } from '../services/api';

export function useMeetingAudio(m: Membership) {
  const app = useApp();
  const session = useRef<AudioSession | null>(null);
  const demo = m.room.mode === 'demo';
  const [muted, setMuted] = useState(demo || m.participant.muted);
  const [outputMuted, setOutputMuted] = useState(false);
  const [status, setStatus] = useState(
    demo ? 'Scripted demo · microphone is not transmitted' : 'Connecting audio…',
  );
  const [error, setError] = useState('');
  const [level, setLevel] = useState(0);
  const [levels, setLevels] = useState<Record<string, number>>({});
  const [working, setWorking] = useState(false);
  const [retry, setRetry] = useState(0);
  const mutedRef = useRef(muted);
  const pending = useRef(false);
  const generation = useRef(0);
  mutedRef.current = muted;
  const outputRef = useRef(outputMuted);
  outputRef.current = outputMuted;

  useEffect(() => {
    generation.current++;
    let disposed = false;
    const controller = new AbortController();
    if (demo) return;
    if (!m.livekit) {
      setStatus('Live audio unavailable');
      return;
    }
    void import('../services/livekit')
      .then(({ connectAudio }) => {
        if (disposed) throw new Error('Audio connection cancelled.');
        return connectAudio(
          m,
          app.preferences.inputDevice,
          app.preferences.outputDevice,
          mutedRef.current,
          (state) => {
            if (!disposed) setStatus(state);
          },
          (id, value) => {
            if (!disposed) {
              if (id === m.participant.id) setLevel(value);
              setLevels((current) => ({ ...current, [id]: value }));
            }
          },
          controller.signal,
        );
      })
      .then((s) => {
        if (disposed) void s.disconnect();
        else {
          session.current = s;
          s.setOutputMuted(outputRef.current);
        }
      })
      .catch((e) => {
        if (!disposed) {
          setStatus('Audio unavailable');
          setError((e as Error).message);
        }
      });
    return () => {
      disposed = true;
      generation.current++;
      controller.abort();
      const current = session.current;
      session.current = null;
      void current?.disconnect();
    };
  }, [m.participant.language, m.session_token, demo, app.preferences.inputDevice, retry]);

  useEffect(() => {
    if (session.current)
      void session.current
        .setOutputDevice(app.preferences.outputDevice)
        .catch((e) => setError((e as Error).message));
  }, [app.preferences.outputDevice]);

  const toggleMic = async () => {
    if (pending.current || demo) return;
    pending.current = true;
    setWorking(true);
    setError('');
    const next = !mutedRef.current;
    const operationGeneration = generation.current;
    try {
      if (!session.current)
        throw new Error(
          'Audio is unavailable. Check the workspace connection before enabling your microphone.',
        );
      await session.current.setMuted(next);
      if (operationGeneration !== generation.current) return;
      const participant = (await updateParticipant(m, { muted: next })) as Participant;
      if (operationGeneration !== generation.current) return;
      setMuted(next);
      app.setMembership({ ...m, participant: { ...m.participant, ...participant, muted: next } });
    } catch (e) {
      if (operationGeneration !== generation.current) return;
      // Any failed state update fails closed, so UI and a resumed tab never imply a muted live microphone.
      try {
        await session.current?.setMuted(true);
      } catch {
        await session.current?.disconnect();
        session.current = null;
        setStatus('Audio disconnected. Reconnect audio in Settings.');
      }
      setMuted(true);
      app.setMembership({ ...m, participant: { ...m.participant, muted: true } });
      setError((e as Error).message);
    } finally {
      pending.current = false;
      setWorking(false);
    }
  };
  const toggleOutput = () => {
    const next = !outputMuted;
    session.current?.setOutputMuted(next);
    setOutputMuted(next);
  };
  return {
    muted,
    outputMuted,
    status,
    error,
    level,
    levels,
    working,
    toggleMic,
    toggleOutput,
    clearError: () => setError(''),
    unlock: async () => {
      try {
        await session.current?.unlock();
      } catch (e) {
        setError((e as Error).message);
      }
    },
    disconnect: async () => {
      await session.current?.disconnect();
      session.current = null;
    },
    retry: () => {
      setError('');
      setRetry((v) => v + 1);
    },
  };
}
