import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { API_BASE, request } from '../services/api';
import { Logo } from './ui';

type Identity = {
  authenticated: boolean;
  configured: boolean;
  email: string | null;
  scope: string | null;
  session_scope: string | null;
  can_host: boolean;
  reviewer?: boolean;
  reviewer_shared_allowed?: boolean;
  admin: boolean;
  password_security_available?: boolean;
};
const Context = createContext<Identity | null>(null);
export const useAccount = () => useContext(Context);
const SIGNED_OUT = 'charcha.signed-out';

function SignOutButton({ recovery = false }: { recovery?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function signOut() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await request<{ continue_url: string }>('/account/logout', { method: 'POST' });
      try {
        localStorage.setItem(SIGNED_OUT, String(Date.now()));
      } catch { /* Tabs with storage disabled recheck on focus. */ }
      window.dispatchEvent(new Event(SIGNED_OUT));
      window.location.replace(result.continue_url);
    } catch {
      setBusy(false);
      setError('Sign-out could not finish. Check your connection and try again.');
    }
  }
  return <><button type="button" disabled={busy} onClick={() => void signOut()}>
    {busy ? 'Signing out…' : recovery ? 'Clear previous sign-in' : 'Sign out'}
  </button>{error && <small role="alert">{error}</small>}</>;
}

export function loginUrl(destination: string, admin = false, google = false) {
  return API_BASE + '/account/login?' + new URLSearchParams({ destination, admin: String(admin), google: String(google) });
}

export function AccountGate({ children }: { children: ReactNode }) {
  const [who, setWho] = useState<Identity | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const lastSession = useRef<string | null>(null);
  const { pathname } = useLocation();
  useEffect(() => {
    let active = true;
    let revision = 0;
    const refresh = async () => {
      const check = ++revision;
      try {
        const status = await request<Identity>('/account', { cache: 'no-store' });
        if (active && check === revision) {
          const previous = lastSession.current;
          if (previous && previous !== status.session_scope) {
            try {
              sessionStorage.removeItem('charcha.membership.' + previous);
              sessionStorage.removeItem('charcha.voice-profile.' + previous);
            } catch { /* Server-side sessions still expire when storage is blocked. */ }
          }
          lastSession.current = status.session_scope;
          setWho(status);
          setError('');
        }
      } catch {
        if (active && check === revision) {
          setWho(null);
          setError('The sign-in service is unreachable. Check your connection and try again.');
        }
      }
    };
    const clearAndRefresh = () => { setWho(null); void refresh(); };
    const onStorage = (event: StorageEvent) => { if (event.key === SIGNED_OUT) clearAndRefresh(); };
    const onVisible = () => { if (document.visibilityState === 'visible') void refresh(); };
    const onPageShow = (event: PageTransitionEvent) => { if (event.persisted) clearAndRefresh(); };
    void refresh();
    const timer = setInterval(refresh, 30000);
    window.addEventListener('focus', refresh);
    window.addEventListener('pageshow', onPageShow);
    window.addEventListener(SIGNED_OUT, clearAndRefresh);
    window.addEventListener('storage', onStorage);
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('charcha-sign-in-required', refresh);
    window.addEventListener('charcha-account-changed', refresh);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('pageshow', onPageShow);
      window.removeEventListener(SIGNED_OUT, clearAndRefresh);
      window.removeEventListener('storage', onStorage);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('charcha-sign-in-required', refresh);
      window.removeEventListener('charcha-account-changed', refresh);
    };
  }, [retry]);
  if (who?.authenticated)
    return (
      <Context.Provider value={who}>
        <div key={who.session_scope} style={{ display: 'contents' }}>
          {children}
        </div>
      </Context.Provider>
    );
  return (
    <main className="account-entry">
      <section className="account-card">
        <Logo />
        <p className="eyebrow">PRIVATE MEETINGS</p>
        <h1>
          {pathname === '/admin' ? 'Workspace administration' : 'A place to understand each other.'}
        </h1>
        <p>
          {pathname.startsWith('/join/')
            ? 'Sign in to request entry to this meeting. Your host will see your verified email before admitting you.'
            : 'Sign in with your email or Google account. Bring a meeting code, choose your language and check that everyone heard you correctly.'}
        </p>
        {who?.configured ? (
          <>
            <div className="account-actions">
              <a className="button primary" href={loginUrl(pathname, pathname === '/admin', !!who.password_security_available)}>
                {pathname === '/admin' ? 'Administrator sign-in' : who.password_security_available ? 'Continue with Google' : 'Continue to sign in'}
              </a>
              {who.password_security_available && pathname !== '/admin' && (
                <a className="button secondary" href={loginUrl(pathname)}>Sign in with a password</a>
              )}
            </div>
            {pathname !== '/admin' && <p className="account-help">
              Reviewing Charcha for Gnani? <a href={loginUrl('/reviewer', false, !!who.password_security_available)}>Reviewer sign-in</a>.
              {' '}Use your verified email and the private invitation supplied by the submitter.
            </p>}
            {who.password_security_available && pathname !== '/admin' && (
              <p className="account-help">First visit? Verify your email with Google, then open Password &amp; security to add a password. You can use either method afterward. Use Google if you forget your password.</p>
            )}
            {who.password_security_available && <div className="account-help">
              <span>Seeing the wrong account? </span><SignOutButton recovery />
            </div>}
          </>
        ) : (
          <div role="status">
            <p>
              {error ||
                (who
                  ? 'Sign-in is waiting for the workspace owner to connect the identity provider.'
                  : 'Checking sign-in…')}
            </p>
            <button className="button secondary" onClick={() => setRetry((r) => r + 1)}>
              Check again
            </button>
          </div>
        )}
        <a className="account-privacy" href="/privacy.html">Privacy</a>
      </section>
    </main>
  );
}

export function AccountMenu() {
  const who = useAccount();
  if (!who) return null;
  return (
    <div className="account-menu">
      <span title={who.email || ''}>{who.email}</span>
      {who.password_security_available && <a href={API_BASE + '/account/security'}>Password &amp; security</a>}
      {(who.admin || (who.can_host && !who.reviewer)) && <Link to="/admin">Admin</Link>}
      <SignOutButton />
    </div>
  );
}
