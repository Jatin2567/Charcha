import { useEffect, useState } from 'react';
import { request } from '../services/api';

type Status = 'none' | 'pending' | 'approved' | 'joining' | 'joined' | 'denied' | 'host';
export function AdmissionGate({ code, children }: { code: string; children: React.ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const path = '/rooms/' + encodeURIComponent(code) + '/admission';
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const r = await request<{ status: Status }>(path);
        if (active) {
          setStatus(r.status);
          setError('');
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    };
    void refresh();
    const timer = setInterval(refresh, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [path]);
  if (status === 'host' || status === 'approved') return <>{children}</>;
  const ask = async () => {
    setBusy(true);
    try {
      const r = await request<{ status: Status }>(status === 'joined' ? path + '/rejoin' : path, {
        method: 'POST',
      });
      setStatus(r.status);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel admission-card">
      <p className="eyebrow">MEETING LOBBY</p>
      <h1>
        {status === 'pending'
          ? 'Waiting for your host'
          : status === 'denied'
            ? 'Your request was declined'
            : status === 'joined'
              ? 'You already joined this meeting'
              : 'Ask to join this meeting'}
      </h1>
      <p role="status">
        {status === 'pending'
          ? 'Your host has your request. This page updates automatically.'
          : status === 'denied'
            ? 'Contact the host if you expected to attend.'
            : status === 'joined'
              ? 'Return to your meeting tab, or disconnect the old device and ask your host to admit this one.'
              : 'The host will see your verified email. Your microphone and camera stay off while you wait.'}
      </p>
      {(status === 'none' || status === 'joined') && (
        <button className="button primary" onClick={() => void ask()} disabled={busy}>
          {status === 'joined' ? 'Disconnect old device and request entry' : 'Ask to join'}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      <a className="text-link" href="#/">
        Back to workspace
      </a>
    </section>
  );
}

type Entry = { id: string; email: string };
export function HostLobby({ code }: { code: string }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const path = '/rooms/' + encodeURIComponent(code) + '/admission/requests';
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const r = await request<{ requests: Entry[] }>(path);
        if (active) {
          setEntries(r.requests);
          setError('');
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    };
    void refresh();
    const timer = setInterval(refresh, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [path]);
  const decide = async (id: string, decision: 'approve' | 'deny') => {
    setBusy(id);
    try {
      await request(path + '/' + id, { method: 'POST', body: JSON.stringify({ decision }) });
      setEntries((list) => list.filter((e) => e.id !== id));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  if (!entries.length && !error) return null;
  return (
    <aside className="host-lobby" aria-label="Join requests">
      <strong aria-live="polite">{entries.length} waiting to join</strong>
      {entries.map((e) => (
        <div key={e.id}>
          <span>{e.email}</span>
          <button
            className="button primary"
            disabled={busy === e.id}
            onClick={() => void decide(e.id, 'approve')}
          >
            Admit
          </button>
          <button
            className="button secondary"
            disabled={busy === e.id}
            onClick={() => void decide(e.id, 'deny')}
          >
            Deny
          </button>
        </div>
      ))}
      {error && <small role="alert">{error}</small>}
    </aside>
  );
}
