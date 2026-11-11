import { useEffect, useRef, useState } from 'react';
import { request } from '../services/api';
import {
  decideReviewerRequest,
  reviewerRequests,
  type ReviewerAccessRequest,
} from '../services/reviewer';
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
  const [applications, setApplications] = useState<ReviewerAccessRequest[]>([]);
  const [approvalHours, setApprovalHours] = useState(72);
  const [approvalShared, setApprovalShared] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [email, setEmail] = useState('');
  const [hours, setHours] = useState(72);
  const [shared, setShared] = useState(true);
  const [created, setCreated] = useState<Invitation | null>(null);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const listRevision = useRef(0);
  async function refresh() {
    const revision = ++listRevision.current;
    const [invitations, requested] = await Promise.all([
      request<{ reviewers: ReviewerGrant[] }>('/admin/reviewers'),
      reviewerRequests(),
    ]);
    if (revision === listRevision.current) {
      setReviewers(invitations.reviewers);
      setApplications(requested.requests);
      setLoaded(true);
    }
  }
  useEffect(() => {
    let active = true;
    const check = async () => {
      const current = ++listRevision.current;
      try {
        const [invitations, requested] = await Promise.all([
          request<{ reviewers: ReviewerGrant[] }>('/admin/reviewers'),
          reviewerRequests(),
        ]);
        if (active && current === listRevision.current) {
          setReviewers(invitations.reviewers);
          setApplications(requested.requests);
          setLoaded(true);
        }
      } catch (e) {
        if (active && current === listRevision.current) setError((e as Error).message);
      }
    };
    const visibleCheck = () => {
      if (document.visibilityState !== 'hidden') void check();
    };
    void check();
    const timer = setInterval(visibleCheck, 30000);
    window.addEventListener('focus', visibleCheck);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener('focus', visibleCheck);
    };
  }, []);
  async function decide(row: ReviewerAccessRequest, decision: 'approve' | 'deny' | 'revoke') {
    setBusy(row.id);
    setError('');
    setMessage('');
    try {
      await decideReviewerRequest(row.id, decision, approvalHours, approvalShared);
      await refresh();
      setMessage(
        decision === 'approve'
          ? `Reviewer access approved for ${row.email}. They can continue from their Reviewer workspace.`
          : decision === 'deny'
            ? `Reviewer access declined for ${row.email}.`
            : `Reviewer access revoked for ${row.email}. Their reviewer resources are being released.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }
  const pending = applications.filter((row) => row.status === 'pending');
  const decided = applications.filter((row) => row.status !== 'pending');
  return (
    <section className="admin-reviewers">
      <h2>Reviewer access and approvals</h2>
      <p>
        Verified email addresses in the configured Gnani domains receive reviewer access
        automatically. Approve other verified accounts here. Email-domain verification does not
        establish a judging role, and reviewer access never includes administrator permissions.
      </p>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      <div className="reviewer-actions">
        <button
          type="button"
          className="button secondary"
          disabled={!!busy}
          onClick={async () => {
            setBusy('refresh');
            setError('');
            try {
              await refresh();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy('');
            }
          }}
        >
          {busy === 'refresh' ? 'Refreshing…' : 'Refresh access requests'}
        </button>
      </div>
      {!loaded && <p role="status">Loading reviewer requests…</p>}
      <section className="reviewer-approval-panel" aria-labelledby="reviewer-pending-title">
        <h3 id="reviewer-pending-title">Pending approval {loaded ? `(${pending.length})` : ''}</h3>
        <div className="reviewer-approval-settings">
          <label className="field">
            <span>New approval duration</span>
            <select
              value={approvalHours}
              onChange={(e) => setApprovalHours(Number(e.target.value))}
            >
              <option value={6}>6 hours</option>
              <option value={24}>24 hours</option>
              <option value={72}>3 days</option>
              <option value={168}>7 days</option>
            </select>
          </label>
          <label className="check-line">
            <input
              type="checkbox"
              checked={approvalShared}
              onChange={(e) => setApprovalShared(e.target.checked)}
            />
            <span>
              Allow shared Gnani and GPU resources for this approval. Their use can consume your
              configured provider credits.
            </span>
          </label>
        </div>
        {pending.length ? (
          <ul className="reviewer-grants reviewer-request-list">
            {pending.map((row) => (
              <li key={row.id}>
                <strong>{row.email}</strong>
                <small>
                  Verified email · Requested {new Date(row.created_at * 1000).toLocaleString()}
                </small>
                <div className="reviewer-actions">
                  <button
                    type="button"
                    className="button primary"
                    disabled={!!busy}
                    aria-label={`Approve ${row.email}`}
                    onClick={() => void decide(row, 'approve')}
                  >
                    {busy === row.id ? 'Saving…' : 'Approve access'}
                  </button>
                  <button
                    type="button"
                    className="button secondary"
                    disabled={!!busy}
                    aria-label={`Deny ${row.email}`}
                    onClick={() => void decide(row, 'deny')}
                  >
                    Deny request
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : loaded ? (
          <p>No requests awaiting approval.</p>
        ) : null}
      </section>
      <h3>Automatic and approved reviewer accounts</h3>
      <p>
        Revocation remains in effect after sign-in. You can approve access again using the duration
        and resource settings above.
      </p>
      {decided.length ? (
        <ul className="reviewer-grants reviewer-request-list">
          {decided.map((row) => (
            <li key={row.id}>
              <strong>{row.email}</strong> · {row.status}
              <small>
                {row.source === 'domain'
                  ? 'Verified Gnani-domain access'
                  : 'Administrator-reviewed request'}
                {row.status === 'approved' && (
                  <> · {row.share_resources ? 'Shared services permitted' : 'Own services only'}</>
                )}
                {row.expires_at != null && (
                  <> · Expires {new Date(row.expires_at * 1000).toLocaleString()}</>
                )}
              </small>
              <div className="reviewer-actions">
                {row.status === 'approved' ? (
                  <button
                    type="button"
                    className="button secondary"
                    disabled={!!busy}
                    aria-label={`Revoke ${row.email}`}
                    onClick={() => void decide(row, 'revoke')}
                  >
                    {busy === row.id ? 'Revoking…' : 'Revoke access'}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="button secondary"
                    disabled={!!busy}
                    aria-label={`Approve again ${row.email}`}
                    onClick={() => void decide(row, 'approve')}
                  >
                    {busy === row.id ? 'Saving…' : 'Approve again'}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : loaded ? (
        <p>No automatic or approved reviewer accounts yet.</p>
      ) : null}
      <details className="reviewer-invite-alternative">
        <summary>Create a private invitation instead</summary>
        <p>Optional one-use access for a recipient who has not requested approval yet.</p>
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
              When supplied, only that verified email can redeem the code. Without an email, the
              first signed-in recipient can redeem it.
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
                Send the code with the Reviewer workspace link. Keep it out of the public
                repository, screenshots and posts.
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
      </details>
      <h3>Current invitations and access</h3>
      <p>
        Revoking active reviewer access also ends their reviewer meetings and releases their
        resources.
      </p>
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
      ) : loaded ? (
        <p>No reviewer invitations yet.</p>
      ) : null}
    </section>
  );
}
