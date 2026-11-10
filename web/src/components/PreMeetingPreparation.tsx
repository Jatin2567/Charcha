import { useEffect, useRef, useState } from 'react';
import { request } from '../services/api';
import { preparationLabel, preparationStatus, type PreparationStatus } from '../services/reviewer';
import '../pages/Reviewer.css';

export function PreMeetingPreparation({ code }: { code: string }) {
  const [status, setStatus] = useState<PreparationStatus | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const revision = useRef(0);
  const changing = useRef(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      if (document.visibilityState !== 'hidden' && !changing.current) {
        const check = revision.current;
        try {
          const result = await preparationStatus(code);
          if (active && check === revision.current) {
            setStatus(result);
            setError('');
          }
        } catch (e) {
          if (active && check === revision.current) {
            setStatus(null);
            setError((e as Error).message);
          }
        }
      }
      if (active) timer = setTimeout(() => void poll(), 3000);
    };
    setStatus(null);
    setError('');
    setBusy(false);
    changing.current = false;
    void poll();
    return () => {
      active = false;
      revision.current++;
      clearTimeout(timer);
    };
  }, [code, retry]);
  async function act(method: 'POST' | 'DELETE') {
    if (changing.current) return;
    const change = ++revision.current;
    changing.current = true;
    setBusy(true);
    setError('');
    try {
      const next = await request<PreparationStatus>(
        `/rooms/${encodeURIComponent(code)}/preparation`,
        { method },
      );
      if (change === revision.current) setStatus(next);
    } catch (e) {
      if (change === revision.current) setError((e as Error).message);
    } finally {
      if (change === revision.current) {
        changing.current = false;
        setBusy(false);
      }
    }
  }
  return (
    <section className="premeeting-preparation" aria-label="Translation preparation">
      <strong>Translation readiness</strong>
      <p role="status">{error ? 'Readiness could not be checked.' : preparationLabel(status)}</p>
      {status?.state === 'starting' && status.elapsed_ms != null && (
        <p>
          Startup elapsed: {Math.floor(status.elapsed_ms / 1000)} seconds. Cold starts can take
          several minutes.
        </p>
      )}
      {status?.state === 'ready' && status.observed_at && (
        <p>Last successful response: {new Date(status.observed_at).toLocaleTimeString()}.</p>
      )}
      {status?.preparation_active && status.preparation_remaining_seconds != null && (
        <p>
          The pre-meeting hold expires in{' '}
          {Math.max(0, Math.ceil(status.preparation_remaining_seconds / 60))} minute(s). Connected
          meetings maintain their own hold.
        </p>
      )}
      {status?.can_prepare && status.available && (
        <div className="reviewer-actions">
          <button
            type="button"
            className="button secondary"
            disabled={busy || status.preparation_active}
            onClick={() => void act('POST')}
          >
            {busy
              ? 'Updating…'
              : status.preparation_active
                ? 'Preparation hold active'
                : 'Prepare translation before joining'}
          </button>
          {status.preparation_active && (
            <button
              type="button"
              className="button secondary"
              disabled={busy}
              onClick={() => void act('DELETE')}
            >
              Cancel preparation hold
            </button>
          )}
        </div>
      )}
      {status?.available && !status.can_prepare && (
        <p>Your host can prepare translation before you join. This status updates automatically.</p>
      )}
      {error && (
        <>
          <p role="alert">{error}</p>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => setRetry((value) => value + 1)}
          >
            Check readiness again
          </button>
        </>
      )}
      <small>
        Preparation can consume GPU credits, including startup and warm idle time. Viewing this
        status does not start compute. Wait for the ready response for a smoother start, or join
        muted while it prepares. Speech and voice enrollment may have separate charges.
      </small>
    </section>
  );
}
