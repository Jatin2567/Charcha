import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, KeyRound, Server, ShieldCheck } from 'lucide-react';
import { request } from '../services/api';
import {
  changeResource,
  reviewerAccess,
  reviewerAccessIsCurrent,
  reviewerWorkspace,
  saveReviewerWorkspace,
  type ReviewerAccess,
  type ReviewerWorkspace,
  type ResourceForm,
} from '../services/reviewer';
import { ErrorNotice, PageHeading } from '../components/ui';
import './Reviewer.css';

const empty: ResourceForm = {
  gnani_source: 'shared',
  evon_source: 'shared',
  gnani_api_key: '',
  evon_base_url: '',
  evon_model: '',
  evon_api_key: '',
  evon_modal_key: '',
  evon_modal_secret: '',
};

export function Reviewer() {
  const navigate = useNavigate();
  const [access, setAccess] = useState<ReviewerAccess | null>(null);
  const [workspace, setWorkspace] = useState<ReviewerWorkspace | null>(null);
  const [form, setForm] = useState<ResourceForm>(empty);
  const [invitation, setInvitation] = useState('');
  const [title, setTitle] = useState('Charcha reviewer meeting');
  const [consent, setConsent] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [confirmClear, setConfirmClear] = useState(false);
  const resourcesLoaded = useRef(false);
  const resourceRevision = useRef(0);
  const currentAccess = useRef<ReviewerAccess | null>(null);

  function loseAccess(value: ReviewerAccess) {
    resourceRevision.current++;
    resourcesLoaded.current = false;
    currentAccess.current = value;
    setAccess({ ...value, can_host: false });
    setWorkspace(null);
    setForm({ ...empty });
    setConsent(false);
    setDirty(false);
    setConfirmClear(false);
    setMessage('Reviewer access has ended. Your private form fields were cleared.');
  }

  function apply(value: ReviewerWorkspace) {
    if (!reviewerAccessIsCurrent(value.access)) {
      loseAccess(value.access);
      return;
    }
    resourceRevision.current++;
    resourcesLoaded.current = true;
    currentAccess.current = value.access;
    setAccess(value.access);
    setWorkspace(value);
    const own = !value.access.reviewer_shared_allowed;
    setForm({
      ...empty,
      gnani_source: own ? 'own' : 'shared',
      evon_source: own ? 'own' : 'shared',
      ...(value.profile
        ? {
            gnani_source: value.profile.gnani_source,
            evon_source: value.profile.evon_source,
            evon_base_url: value.profile.evon_base_url || '',
            evon_model: value.profile.evon_model || '',
          }
        : {}),
    });
    setConsent(false);
    setDirty(false);
    setConfirmClear(false);
  }
  async function refresh() {
    const current = await reviewerAccess();
    setAccess(current);
    if (current.can_host) apply(await reviewerWorkspace());
  }
  useEffect(() => {
    let active = true;
    let requestRevision = 0;
    let expiryTimer: ReturnType<typeof setTimeout>;
    const check = async () => {
      const revision = ++requestRevision;
      try {
        const current = await reviewerAccess();
        if (!active || revision !== requestRevision) return;
        setError((previous) =>
          previous.startsWith('Reviewer access could not be verified.') ? '' : previous,
        );
        clearTimeout(expiryTimer);
        currentAccess.current = current;
        if (!reviewerAccessIsCurrent(current)) {
          if (resourcesLoaded.current) loseAccess(current);
          else setAccess({ ...current, can_host: false });
          return;
        }
        setAccess(current);
        if (current.reviewer && current.expires_at != null) {
          expiryTimer = setTimeout(
            () => {
              if (active && !reviewerAccessIsCurrent(currentAccess.current)) {
                loseAccess(currentAccess.current!);
                void check();
              }
            },
            Math.max(0, current.expires_at * 1000 - Date.now()) + 25,
          );
        }
        if (!resourcesLoaded.current) {
          const resourceCheck = resourceRevision.current;
          const result = await reviewerWorkspace();
          if (active && revision === requestRevision && resourceCheck === resourceRevision.current)
            apply(result);
        }
      } catch (e) {
        if (active && revision === requestRevision) {
          setAccess(null);
          setError('Reviewer access could not be verified. ' + (e as Error).message);
        }
      }
    };
    const onVisible = () => {
      if (document.visibilityState !== 'hidden') void check();
    };
    void check();
    const timer = setInterval(onVisible, 30000);
    window.addEventListener('focus', onVisible);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      active = false;
      clearInterval(timer);
      clearTimeout(expiryTimer);
      window.removeEventListener('focus', onVisible);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);
  function change<K extends keyof ResourceForm>(key: K, value: ResourceForm[K]) {
    setForm((previous) => changeResource(previous, key, value));
    setDirty(true);
    setConsent(false);
    setMessage('');
  }
  const allowed = !!access?.reviewer_shared_allowed;
  const hostAllowed = reviewerAccessIsCurrent(access);
  const sourcesAllowed = allowed || (form.gnani_source === 'own' && form.evon_source === 'own');
  const sameEvon =
    workspace?.profile?.evon_source === 'own' &&
    form.evon_base_url.trim() === workspace.profile.evon_base_url;
  return (
    <div className="reviewer-page">
      <PageHeading
        eyebrow="GNANI CHALLENGE · REVIEWER WORKSPACE"
        title="Explore Charcha on your terms."
        description="Create your own meeting, admit your participants and choose which speech and model services power your evaluation."
      />
      <div className="reviewer-steps" aria-label="Reviewer setup steps">
        <span>
          <b>1</b> Sign in &amp; redeem an invitation
        </span>
        <span>
          <b>2</b> Choose your resources
        </span>
        <span>
          <b>3</b> Prepare, then join
        </span>
      </div>
      <ErrorNotice message={error} onDismiss={() => setError('')} />
      {message && (
        <p className="notice info" role="status">
          {message}
        </p>
      )}
      {!access && !error && <p role="status">Checking reviewer access…</p>}
      {access && !hostAllowed && (
        <section className="panel reviewer-invitation">
          <ShieldCheck size={25} />
          <h2>Reviewer invitation</h2>
          <p>
            Sign-in verifies your email. A private invitation from the Charcha administrator gives
            you meeting-host access; it does not give administrator access.
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy('redeem');
              setError('');
              try {
                await request('/reviewer/access/redeem', {
                  method: 'POST',
                  body: JSON.stringify({ invitation: invitation.trim() }),
                });
                setInvitation('');
                await refresh();
                window.dispatchEvent(new Event('charcha-account-changed'));
                setMessage('Invitation accepted. Choose the resources for your review.');
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy('');
              }
            }}
          >
            <label className="field">
              <span>Private one-use invitation</span>
              <input
                type="password"
                autoComplete="off"
                required
                value={invitation}
                onChange={(e) => setInvitation(e.target.value)}
                placeholder="Paste the invitation supplied to you"
              />
            </label>
            <button className="button primary" disabled={!!busy || !invitation.trim()}>
              {busy === 'redeem' ? 'Checking invitation…' : 'Activate reviewer access'}
            </button>
          </form>
          <p className="source-note">
            Ask the submitter for a fresh invitation if yours has expired. Keep invitation codes out
            of public posts and URLs.
          </p>
        </section>
      )}
      {hostAllowed && access && (
        <>
          <section className="panel reviewer-status">
            <ShieldCheck size={24} />
            <div>
              <strong>
                {access.reviewer ? 'Reviewer meeting access enabled' : 'Designated host workspace'}
              </strong>
              <p>
                {allowed
                  ? 'Your access allows shared Charcha services or your own services.'
                  : 'Use your own speech and GPU services. This invitation does not allow shared provider credits.'}
                {access.expires_at && (
                  <> Access expires {new Date(access.expires_at * 1000).toLocaleString()}.</>
                )}
              </p>
            </div>
          </section>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!consent || !reviewerAccessIsCurrent(currentAccess.current)) return;
              const resourceCheck = resourceRevision.current;
              setBusy('save');
              setError('');
              try {
                const saved = await saveReviewerWorkspace(form);
                if (resourceCheck !== resourceRevision.current) return;
                apply(saved);
                setMessage(
                  'Resource choices saved for this sign-in session. No speech or GPU request was started.',
                );
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy('');
              }
            }}
          >
            <div className="reviewer-resource-grid">
              <section className="panel">
                <KeyRound size={25} />
                <h2>Speech · Gnani</h2>
                <label className="field">
                  <span>Speech credentials</span>
                  <select
                    value={form.gnani_source}
                    onChange={(e) =>
                      change('gnani_source', e.target.value as ResourceForm['gnani_source'])
                    }
                  >
                    <option value="shared" disabled={!allowed}>
                      Use Charcha’s configured Gnani key
                    </option>
                    <option value="own">Use my own Gnani key</option>
                  </select>
                </label>
                {form.gnani_source === 'own' ? (
                  <label className="field">
                    <span>Gnani API key</span>
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={form.gnani_api_key}
                      onChange={(e) => change('gnani_api_key', e.target.value)}
                      placeholder={
                        workspace?.profile?.gnani_source === 'own' &&
                        workspace.profile.gnani_key_set
                          ? 'Stored privately — leave blank to keep'
                          : 'Paste your Gnani speech API key'
                      }
                    />
                    <small>
                      Used for recognition, synthesis and consented voice enrollment in your
                      reviewer meetings.
                    </small>
                  </label>
                ) : (
                  <p>
                    Uses the application’s existing speech service, while access and provider
                    credits are available. The key is never shown to you.
                  </p>
                )}
              </section>
              <section className="panel">
                <Server size={25} />
                <h2>Translation · Evon GPU</h2>
                <label className="field">
                  <span>Translation service</span>
                  <select
                    value={form.evon_source}
                    onChange={(e) =>
                      change('evon_source', e.target.value as ResourceForm['evon_source'])
                    }
                  >
                    <option value="shared" disabled={!allowed}>
                      Use Charcha’s configured Evon service
                    </option>
                    <option value="own">Connect my own Evon endpoint</option>
                  </select>
                </label>
                {form.evon_source === 'own' ? (
                  <>
                    <label className="field">
                      <span>HTTPS model base URL</span>
                      <input
                        type="url"
                        required
                        value={form.evon_base_url}
                        onChange={(e) => change('evon_base_url', e.target.value)}
                        placeholder="https://your-service.modal.run/v1"
                      />
                      <small>
                        Deploy Evon first. Modal HTTPS endpoints are supported; other server origins
                        need the administrator’s allowlist. Do not paste SSH, GCP or Modal workspace
                        credentials. Changing this address clears typed model credentials; enter the
                        credentials for the new endpoint.
                      </small>
                    </label>
                    <label className="field">
                      <span>Served model name</span>
                      <input
                        required
                        value={form.evon_model}
                        onChange={(e) => change('evon_model', e.target.value)}
                        placeholder="Exact model name configured in your server"
                      />
                    </label>
                    <label className="field">
                      <span>Model API key, if required</span>
                      <input
                        type="password"
                        autoComplete="new-password"
                        value={form.evon_api_key}
                        onChange={(e) => change('evon_api_key', e.target.value)}
                        placeholder={
                          sameEvon && workspace?.profile?.evon_key_set
                            ? 'Stored privately — leave blank to keep'
                            : 'Bearer key for this model endpoint only'
                        }
                      />
                    </label>
                    <details>
                      <summary>Modal proxy authentication, if enabled</summary>
                      <p>
                        Use the proxy credential pair for this HTTPS endpoint, not your Modal CLI
                        login token.
                      </p>
                      <label className="field">
                        <span>Modal-Key</span>
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={form.evon_modal_key}
                          onChange={(e) => change('evon_modal_key', e.target.value)}
                          placeholder={
                            sameEvon && workspace?.profile?.modal_proxy_set
                              ? 'Stored privately — leave blank to keep'
                              : ''
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Modal-Secret</span>
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={form.evon_modal_secret}
                          onChange={(e) => change('evon_modal_secret', e.target.value)}
                          placeholder={
                            sameEvon && workspace?.profile?.modal_proxy_set
                              ? 'Stored privately — leave blank to keep'
                              : ''
                          }
                        />
                      </label>
                    </details>
                  </>
                ) : (
                  <p>
                    Uses the shared model. Preparation may take several minutes when it has scaled
                    down. Availability depends on the provider and remaining compute credits.
                  </p>
                )}
              </section>
            </div>
            <section className="panel reviewer-consent">
              <p>
                Saved credentials stay on the server for this sign-in session and are never written
                to browser storage. Changes apply to new reviewer meetings. Deleting the
                configuration also ends meetings using your reviewer resources.
              </p>
              <label className="check-line">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                <span>
                  I am authorized to use these services and understand that GPU preparation, warm
                  idle time, speech and voice enrollment can consume the selected provider’s
                  credits.
                </span>
              </label>
              <div className="reviewer-actions">
                <button className="button primary" disabled={!!busy || !consent}>
                  {busy === 'save' ? 'Saving…' : 'Save resource choices'}
                </button>
                {workspace?.profile && !confirmClear && (
                  <button
                    type="button"
                    className="button secondary"
                    disabled={!!busy}
                    onClick={() => setConfirmClear(true)}
                  >
                    Delete saved configuration…
                  </button>
                )}
              </div>
              {confirmClear && (
                <div className="notice warning">
                  <div>
                    <strong>End reviewer meetings and delete credentials?</strong>
                    <p>
                      This clears your saved service choices and closes meetings using these
                      resources. Other participants in those meetings will need a new invitation.
                    </p>
                    <div className="reviewer-actions">
                      <button
                        type="button"
                        className="button secondary"
                        disabled={!!busy}
                        onClick={() => setConfirmClear(false)}
                      >
                        Keep configuration
                      </button>
                      <button
                        type="button"
                        className="button danger"
                        disabled={!!busy}
                        onClick={async () => {
                          setBusy('clear');
                          setError('');
                          try {
                            await request('/reviewer/workspace', { method: 'DELETE' });
                            await refresh();
                            setMessage(
                              'Reviewer configuration cleared. Associated meetings have ended.',
                            );
                          } catch (e) {
                            setError((e as Error).message);
                          } finally {
                            setBusy('');
                          }
                        }}
                      >
                        {busy === 'clear' ? 'Ending meetings…' : 'End meetings and delete'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </section>
          </form>
          <section className="panel reviewer-start">
            <h2>Start your evaluation</h2>
            <p>
              Create a meeting, then use <strong>Prepare translation before joining</strong> on the
              next screen. Wait for a measured ready response before starting the conversation.
            </p>
            <label className="field">
              <span>Meeting title</span>
              <input value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} />
            </label>
            {!workspace?.configured && workspace?.missing?.length ? (
              <p className="source-note">Setup needed: {workspace.missing.join(', ')}</p>
            ) : null}
            {dirty && (
              <p className="source-note">
                Save your changed resource choices before creating a meeting.
              </p>
            )}
            {!sourcesAllowed && (
              <p role="alert">
                Shared resources are no longer allowed by your invitation. Choose and save your own
                services before creating a meeting.
              </p>
            )}
            <button
              className="button primary"
              disabled={
                !!busy ||
                !hostAllowed ||
                !sourcesAllowed ||
                dirty ||
                !workspace?.configured ||
                !title.trim()
              }
              onClick={async () => {
                if (!reviewerAccessIsCurrent(currentAccess.current)) return;
                setBusy('create');
                setError('');
                try {
                  const room = await request<{ code: string }>('/rooms', {
                    method: 'POST',
                    body: JSON.stringify({
                      title: title.trim(),
                      audio_mode: 'interpreted',
                      resource_mode: 'reviewer',
                    }),
                  });
                  navigate('/join/' + room.code);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy('');
                }
              }}
            >
              {busy === 'create' ? 'Creating your meeting…' : 'Create reviewer meeting'}
              <ArrowRight size={17} />
            </button>
            <p className="source-note">
              Invite other signed-in participants and admit them yourself. All configured language
              options remain available. Your own providers have their own pricing, quotas and
              capacity; Charcha cannot remove those limits.
            </p>
          </section>
        </>
      )}
      <p>
        <Link to="/tests">Open the test lab</Link> ·{' '}
        <a
          href="https://github.com/Jatin2567/Charcha/blob/main/docs/REVIEWER_GUIDE.md"
          target="_blank"
          rel="noreferrer"
        >
          Reviewer setup guide
        </a>
      </p>
    </div>
  );
}
