import { useEffect, useState } from 'react';
import { request } from '../services/api';
import { useAccount, loginUrl } from '../components/AccountGate';
import { AdminGnaniBudget } from '../components/AdminGnaniBudget';
import { AdminReviewers } from '../components/AdminReviewers';

type Summary = {
  host_email: string;
  changes: { at: number; email: string }[];
  rooms: { code: string; title: string; waiting: number; participants: number }[];
};
export function AdminPage() {
  const who = useAccount();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!who?.admin) return;
    let active = true;
    void request<Summary>('/admin')
      .then((r) => {
        if (active) {
          setSummary(r);
          setEmail(r.host_email);
        }
      })
      .catch((e) => {
        if (active) setMessage(e.message);
      });
    return () => {
      active = false;
    };
  }, [who?.admin]);
  if (!who?.admin)
    return (
      <section className="panel admin-access">
        <h1>Workspace administration</h1>
        <p>Use your administrator username, password and second factor to continue.</p>
        <a className="button primary" href={loginUrl('/admin', true)}>
          Administrator sign-in
        </a>
      </section>
    );
  return (
    <section className="panel admin-access">
      <p className="eyebrow">RESTRICTED ACCESS</p>
      <h1>Workspace administration</h1>
      <p>
        Manage who can host new meetings. Existing rooms keep their original host until they expire.
      </p>
      {summary && (
        <>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setSaving(true);
              try {
                const r = await request<{ host_email: string }>('/admin/host', {
                  method: 'POST',
                  body: JSON.stringify({ email }),
                });
                setSummary(await request<Summary>('/admin'));
                setEmail(r.host_email);
                setMessage('Meeting host updated.');
              } catch (e) {
                setMessage((e as Error).message);
              } finally {
                setSaving(false);
              }
            }}
          >
            <label>
              Designated host email
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <button
              className="button primary"
              disabled={saving || email.trim() === summary.host_email}
            >
              Save host
            </button>
          </form>
          <AdminGnaniBudget />
          <AdminReviewers />
          <h2>Active meetings</h2>
          {summary.rooms.length ? (
            <ul>
              {summary.rooms.map((r) => (
                <li key={r.code}>
                  <strong>{r.title}</strong> · {r.participants} in meeting · {r.waiting} waiting
                </li>
              ))}
            </ul>
          ) : (
            <p>No active meetings.</p>
          )}
          <h2>Recent host changes</h2>
          {summary.changes.length ? (
            <ul>
              {summary.changes.map((c) => (
                <li key={c.at}>
                  {new Date(c.at * 1000).toLocaleString()} · {c.email}
                </li>
              ))}
            </ul>
          ) : (
            <p>No host changes yet.</p>
          )}
        </>
      )}
      <p role="status">{message}</p>
    </section>
  );
}
