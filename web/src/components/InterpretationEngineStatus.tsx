import { useEffect, useState } from 'react';
import {
  engineScopeLabel,
  engineStatus,
  type EngineStatus,
} from '../services/interpretationEngine';
import type { Membership } from '../types/domain';

export function InterpretationEngineStatus({ membership }: { membership?: Membership }) {
  const [status, setStatus] = useState<EngineStatus | null>(null);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await engineStatus(membership);
        if (active) setStatus(value);
      } catch {
        if (active) setStatus(null);
      }
      if (active) timer = setTimeout(() => void poll(), 2000);
    };
    setStatus(null);
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [membership?.room.code, membership?.session_token]);
  const labels = {
    idle: 'Interpretation starts when meeting audio connects. A cold start may take several minutes.',
    starting:
      'Preparing interpretation for your meeting. You can set up your voice while the model loads.',
    ready: 'Interpretation responded successfully. Active meetings keep it ready through pauses.',
    unavailable: 'Interpretation is unavailable. Connected meetings retry automatically.',
    external: 'Model readiness is not measured.',
  };
  return (
    <div className="notice info" role="status">
      <div>
        <strong>{engineScopeLabel(status, !!membership)}</strong>
        <p>
          {status?.scope === 'none' || status?.scope === 'multiple'
            ? status.detail || 'Choose a current meeting to inspect its engine.'
            : status
              ? labels[status.state]
              : 'Interpretation status unavailable.'}
        </p>
        {status?.detail && !['none', 'multiple'].includes(status.scope || '') && (
          <p>{status.detail}</p>
        )}
        {status?.state === 'starting' && status.elapsed_ms != null && (
          <p>Startup elapsed: {Math.floor(status.elapsed_ms / 1000)} seconds</p>
        )}
        {status?.startup_ms != null && (
          <p>Last measured startup: {(status.startup_ms / 1000).toFixed(1)} seconds.</p>
        )}
        {status?.lifecycle === 'meeting' &&
          status.active_meetings != null &&
          status.scope !== 'multiple' && (
            <p>Meetings holding this engine: {status.active_meetings}</p>
          )}
        <small>
          Opening this page does not start compute. Readiness is a measured service response, not a
          live GPU allocation report. Connected meetings and active preparation can hold the
          selected engine warm. After those holds end, shutdown follows that provider’s scaling
          settings; Charcha does not shut down externally managed VMs.
        </small>
      </div>
    </div>
  );
}
