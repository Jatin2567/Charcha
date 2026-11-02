import { useCallback, useEffect, useRef, useState } from 'react';
import type { Membership } from '../types/domain';
import { ConferenceRequestError, fetchConferenceReadiness } from '../services/conferenceReadiness';
import type { ConferenceReadiness } from '../services/conferenceReadiness';

export function useConferenceReadiness(m: Membership) {
  const [report, setReport] = useState<ConferenceReadiness | null>(null);
  const [error, setError] = useState('');
  const [stale, setStale] = useState(false);
  const generation = useRef(0);
  const latest = useRef(m);
  latest.current = m;
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const version = generation.current;
    try {
      const next = await fetchConferenceReadiness(latest.current, signal);
      if (version === generation.current && !signal?.aborted) {
        setReport(next);
        setError('');
        setStale(!next.membership.active);
      }
      return next;
    } catch (issue) {
      if (version === generation.current && !signal?.aborted) {
        setReport(null);
        setError(issue instanceof Error ? issue.message : 'Room readiness is unavailable.');
        setStale(issue instanceof ConferenceRequestError && issue.staleMembership);
      }
      throw issue;
    }
  }, []);
  useEffect(() => {
    generation.current++;
    setReport(null);
    setError('');
    setStale(false);
    if (m.localDemo || m.room.mode === 'demo') return;
    let disposed = false,
      busy = false;
    let controller: AbortController | null = null;
    const poll = async () => {
      if (disposed || busy || document.hidden) return;
      busy = true;
      controller = new AbortController();
      try {
        await refresh(controller.signal);
      } catch {
        /* The visible state carries the safe failure. */
      } finally {
        busy = false;
      }
    };
    const visibility = () => {
      if (document.hidden) controller?.abort();
      if (!document.hidden) void poll();
    };
    void poll();
    const interval = setInterval(() => void poll(), 1000);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      disposed = true;
      generation.current++;
      controller?.abort();
      clearInterval(interval);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [m.room.code, m.session_token, m.participant.language, m.room.mode, m.localDemo, refresh]);
  return { report, error, stale, refresh };
}
