import { useEffect, useState } from 'react';
import { request } from '../services/api';
import '../pages/Reviewer.css';

type ReviewerGrant = {
  id: string;
  recipient_email: string | null;
  email: string | null;
  created_at: number;
  expires_at: number;
  share_resources: boolean;
  status: 'pending' | 'active' | 'expired' | 'revoked';
};
type Invitation = ReviewerGrant & { invitation: string };

export function AdminReviewers() {
  const [reviewers, setReviewers] = useState<ReviewerGrant[]>([]);
  const [email, setEmail] = useState('');
  const [hours, setHours] = useState(72);
  const [shared, setShared] = useState(true);
  const [created, setCreated] = useState<Invitation | null>(null);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  async function refresh() {
    setReviewers((await request<{ reviewers: ReviewerGrant[] }>('/admin/reviewers')).reviewers);
  }
  useEffect(() => {
    let active = true;
    void request<{ reviewers: ReviewerGrant[] }>('/admin/reviewers')
      .then((result) => {
        if (active) setReviewers(result.reviewers);
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <section className="admin-reviewers">
      <h2>Gnani reviewer invitations</h2>
      <p>
        Give a reviewer permission to create their own meetings and admit participants. Reviewers
        use the normal verified-email sign-in and never receive administrator access.
      </p>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy('create');
          setError('');
          setMessage('');
          setCreated(null);
          try {
            const value = await request<Invitation>('/admin/reviewer-invitations', {
              method: 'POST',
              body: JSON.stringify({
                recipient_email: email.trim() || null,
                expires_in_hours: hours,
                share_resources: shared,
              }),
            });
            setCreated(value);
            await refresh();
            setMessage(
              'One-use invitation created. Share it privately with the intended reviewer.',
            );
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy('');
          }
        }}
      >
        <label className="field">
          <span>Reviewer email, recommended</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="reviewer@example.com"
          />
          <small>
            When supplied, only that verified email can redeem the code. Without an email, the first
            signed-in recipient can redeem it.
          </small>
        </label>
        <label className="field">
          <span>Access expires after</span>
          <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            <option value={6}>6 hours</option>
            <option value={24}>24 hours</option>
            <option value={72}>3 days</option>
            <option value={168}>7 days</option>
          </select>
        </label>
        <label className="check-line">
          <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
          <span>
            Allow Charcha’s shared Gnani and GPU resources. Reviewer activity can consume your
            configured provider credits. Otherwise the reviewer must connect their own services.
          </span>
        </label>
        <button className="button primary" disabled={!!busy} style={{ marginTop: 14 }}>
          {busy === 'create' ? 'Creating…' : 'Create reviewer invitation'}
        </button>
      </form>
      {created && (
        <div className="notice info">
          <div>
            <strong>Private invitation · shown once</strong>
            <p>
              Send the code with the Reviewer workspace link. Keep it out of the public repository,
              screenshots and posts.
            </p>
            <textarea
              aria-label="New private reviewer invitation"
              readOnly
              value={created.invitation}
            />
            <p>Expires {new Date(created.expires_at * 1000).toLocaleString()}.</p>
            <div className="reviewer-actions">
              <button
                className="button secondary"
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(created.invitation);
                    setMessage('Invitation copied.');
                  } catch {
                    setError('Clipboard unavailable. Select and copy the invitation manually.');
                  }
                }}
              >
                Copy invitation
              </button>
              <button className="button secondary" type="button" onClick={() => setCreated(null)}>
                Hide invitation
              </button>
            </div>
          </div>
        </div>
      )}
      <h3>Current invitations and access</h3>
      <p>Revoking active reviewer access also ends their reviewer meetings and releases their resources.</p>
      {reviewers.length ? (
        <ul className="reviewer-grants">
          {reviewers.map((row) => (
            <li key={row.id}>
              <strong>{row.email || row.recipient_email || 'Unbound private invitation'}</strong> ·{' '}
              {row.status}
              <small>
                {row.share_resources ? 'Shared services permitted' : 'Own services only'} · Expires{' '}
                {new Date(row.expires_at * 1000).toLocaleString()}
              </small>
              {['pending', 'active'].includes(row.status) && (
                <button
                  type="button"
                  className="button secondary"
                  disabled={!!busy}
                  onClick={async () => {
                    setBusy(row.id);
                    setError('');
                    try {
                      await request('/admin/reviewers/' + encodeURIComponent(row.id), {
                        method: 'DELETE',
                      });
                      if (created?.id === row.id) setCreated(null);
                      await refresh();
                      setMessage(
                        'Reviewer access revoked. Their reviewer resources are being released.',
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy('');
                    }
                  }}
                >
                  {busy === row.id ? 'Revoking…' : 'Revoke access'}
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p>No reviewer invitations yet.</p>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
