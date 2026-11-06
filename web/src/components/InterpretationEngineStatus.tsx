import { useEffect, useState } from 'react';
import { engineStatus, type EngineStatus } from '../services/interpretationEngine';
import type { Membership } from '../types/domain';

export function InterpretationEngineStatus({ membership }: { membership?: Membership }) {
  const [status, setStatus] = useState<EngineStatus | null>(null);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const value = await engineStatus(membership); if (active) setStatus(value); }
      catch { if (active) setStatus(null); }
      if (active) timer = setTimeout(() => void poll(), 2000);
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [membership?.room.code, membership?.session_token]);
  const labels = {
    idle: 'Interpretation starts when meeting audio connects. A cold start may take several minutes.',
    starting: 'Preparing interpretation for your meeting. You can set up your voice while the model loads.',
    ready: 'Interpretation responded successfully. Active meetings keep it ready through pauses.',
    unavailable: 'Interpretation is unavailable. Connected meetings retry automatically.',
    external: 'Model readiness is not measured.',
  };
  return <div className="notice info" role="status">
    <div><strong>{status ? labels[status.state] : 'Interpretation status unavailable.'}</strong>
      {status?.state === 'starting' && status.elapsed_ms != null &&
        <p>Startup elapsed: {Math.floor(status.elapsed_ms / 1000)} seconds</p>}
      {status?.startup_ms != null && <p>Last measured startup: {(status.startup_ms / 1000).toFixed(1)} seconds.</p>}
      {status?.lifecycle === 'meeting' && <p>Meetings keeping interpretation ready: {status.active_meetings ?? 0}</p>}
      <small>One GPU is shared across active meetings. It stays warm during silence and scales down after the last meeting disconnects. Opening this page does not start it. Readiness is a measured response, not a live GPU allocation report.</small>
    </div>
  </div>;
}
