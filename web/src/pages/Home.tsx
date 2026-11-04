import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ArrowRight,
  Plus,
  Link2,
  AudioLines,
  Languages,
  ShieldCheck,
  ArrowUpRight,
  CalendarDays,
  ChevronRight,
  MoveUpRight,
  Sparkles,
  Check,
  Globe2,
  FileCheck2,
} from 'lucide-react';
import { Avatar, Badge, ErrorNotice, Modal } from '../components/ui';
import { ConversationIllustration } from '../components/ConversationIllustration';
import { useApp } from '../state/AppContext';
import { createRoom } from '../services/api';
import { languageName } from '../types/domain';
export function Home() {
  const app = useApp();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [join, setJoin] = useState(false);
  const [code, setCode] = useState('');
  const [title, setTitle] = useState('Cross-language conversation');
  const start = async () => {
    setBusy(true);
    setError('');
    try {
      if (!app.health)
        throw new Error(app.serviceError || 'The workspace is still connecting. Please try again.');
      const room = await createRoom(title);
      navigate(`/join/${room.code}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const joinCode = (value: string) => {
    let cleaned = value.trim();
    try {
      const url = new URL(cleaned);
      cleaned =
        (url.hash ? url.hash.slice(1) : url.pathname).split('/').filter(Boolean).pop() || '';
    } catch {
      /* allow a room code */
    }
    if (!/^[a-zA-Z0-9_-]{6,100}$/.test(cleaned)) {
      setError('Enter a valid invitation code or full invitation link.');
      return;
    }
    navigate(`/join/${encodeURIComponent(cleaned)}`);
  };
  const date = new Date().toLocaleDateString('en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  return (
    <>
      <div className="home-challenge-pill" role="banner">
        <div className="home-challenge-left">
          <Badge tone="green">Gnani.ai Challenge Submission</Badge>
          <span>Sovereign Multi-Party Indic Voice &amp; Coordination Gateway</span>
        </div>
        <Link to="/impact" className="home-challenge-cta">
          Explore Challenge Story, Architecture &amp; Empirical Evidence &rarr;
        </Link>
      </div>
      <div className="home-heading">
        <div>
          <div className="eyebrow">A LITTLE CLOSER, IN EVERY LANGUAGE</div>
          <h1>
            Good conversations.
            <br />
            <span>No language barriers.</span>
          </h1>
          <p>
            Your voice, their language. A shared space to listen,
            <br className="desktop-br" /> understand, and move things forward.
          </p>
        </div>
        <span className="today">
          <CalendarDays size={15} />
          {date}
        </span>
      </div>
      <ErrorNotice message={error} onDismiss={() => setError('')} />
      <section className="home-hero">
        <div className="hero-copy">
          <Badge tone="green">
            <span className="status-dot" />
            MEANING CONNECTS US
          </Badge>
          <h2>
            Different languages.
            <br />
            Same conversation.
          </h2>
          <p>
            Bring everyone to the table. Speak naturally,
            <br className="desktop-br" /> and hear the conversation in your language.
          </p>
          <button
            className="button primary large"
            onClick={() => void start()}
            disabled={busy || app.healthLoading}
          >
            <Plus size={19} />
            {busy ? 'Creating your room…' : 'New conversation'}
            <ArrowRight size={18} />
          </button>
          <button
            className="join-inline"
            onClick={() => {
              setJoin(true);
              setError('');
            }}
          >
            <Link2 size={16} />
            Have an invite? <strong>Join a conversation</strong>
            <ArrowUpRight size={15} />
          </button>
          <div className="hero-footnote">
            <ShieldCheck size={14} />
            You choose when to enable your microphone.
          </div>
        </div>
        <div
          className="conversation-art conversation-art-illustrated"
          aria-label="Illustration of Hindi, Tamil and Bengali voices meeting in one conversation"
        >
          <div className="illustration-languages" aria-hidden="true">
            <span lang="hi">नमस्ते</span>
            <span lang="ta">வணக்கம்</span>
            <span lang="bn">নমস্কার</span>
          </div>
          <ConversationIllustration />
          <p className="illustration-caption">One conversation. Many perspectives.</p>
        </div>
      </section>
      <section className="feature-strip" aria-label="Workspace capabilities">
        <div>
          <span className="feature-icon green">
            <Languages size={21} />
          </span>
          <span>
            <strong>Speak in your mother tongue</strong>
            <small>Hindi, Tamil, Bengali, Telugu &amp; Marathi — speak naturally</small>
          </span>
        </div>
        <div>
          <span className="feature-icon orange">
            <AudioLines size={21} />
          </span>
          <span>
            <strong>Natural speech understanding</strong>
            <small>Real-time interpretation without awkward delay or hesitation</small>
          </span>
        </div>
        <div>
          <span className="feature-icon blue">
            <ShieldCheck size={21} />
          </span>
          <span>
            <strong>Trust every agreed detail</strong>
            <small>Dual captions highlight prices, dates &amp; commitments</small>
          </span>
        </div>
      </section>
      <div className="home-lower">
        <section className="recent-section">
          <div className="section-title">
            <div>
              <h2>Your conversations</h2>
              <p>Good ideas deserve a place to come back to.</p>
            </div>
            <Link className="text-link" to="/history">
              View all
              <ArrowUpRight size={15} />
            </Link>
          </div>
          {app.recaps.length ? (
            <div className="recent-list">
              {app.recaps.slice(0, 3).map((r) => (
                <button
                  className="recent-row"
                  key={r.id}
                  onClick={() => {
                    app.setLatestRecap(r);
                    navigate(`/recap/${r.id}`);
                  }}
                >
                  <span className="recent-icon">
                    <AudioLines size={20} />
                  </span>
                  <span>
                    <strong>{r.room.title}</strong>
                    <small>
                      {new Date(r.ended_at).toLocaleDateString('en-IN', {
                        day: 'numeric',
                        month: 'short',
                      })}{' '}
                      <span>·</span> {r.turns.length} transcript turns
                    </small>
                  </span>
                  <div className="avatar-stack">
                    {r.room.participants
                      .filter((p) => !p.is_agent)
                      .slice(0, 3)
                      .map((p, i) => (
                        <Avatar key={p.id} name={p.name} index={i} />
                      ))}
                  </div>
                  <ChevronRight size={17} />
                </button>
              ))}
            </div>
          ) : (
            <div className="first-conversation">
              <span className="first-icon">
                <AudioLines size={26} />
              </span>
              <h3>Make room for your first conversation.</h3>
              <p>
                Saved recaps will appear here. Nothing is saved
                <br className="desktop-br" /> to this device until you choose to keep it.
              </p>
              <button className="text-link" onClick={() => void start()}>
                Let’s start talking
                <ArrowRight size={15} />
              </button>
            </div>
          )}
        </section>
        <aside className="workspace-card">
          <div className="workspace-card-top">
            <span className="feature-icon green">
              <Globe2 size={21} />
            </span>
            <span className="eyebrow">YOUR SPACE, SET UP FOR YOU</span>
          </div>
          <h3>
            A good conversation
            <br />
            starts with a sound check.
          </h3>
          <div className="setup-item">
            <span>
              <Check size={13} />
            </span>
            <div>
              <small>Listening language</small>
              <strong>{languageName(app.preferences.language)}</strong>
            </div>
            <Link to="/settings" aria-label="Edit listening language">
              <MoveUpRight size={17} />
            </Link>
          </div>
          <div className="setup-item">
            <span className={app.health ? '' : 'pending'}>
              {app.health ? <Check size={13} /> : <span>!</span>}
            </span>
            <div>
              <small>Workspace mode</small>
              <strong>
                {app.health?.mode === 'live'
                  ? 'Live interpretation'
                  : app.health?.mode === 'transport'
                    ? 'Local original audio test'
                    : app.health
                      ? 'Scripted demonstration'
                      : 'Service setup needed'}
              </strong>
            </div>
            <Link to="/settings" aria-label="View workspace setup">
              <MoveUpRight size={17} />
            </Link>
          </div>
          <Link to="/settings" className="button secondary full">
            Check your setup
            <ArrowUpRight size={16} />
          </Link>
          <Link
            to="/impact"
            className="button text-link full"
            style={{ marginTop: 8, justifyContent: 'center', fontSize: '12px' }}
          >
            <FileCheck2 size={14} />
            Challenge Story, Evidence &amp; Impact
            <ArrowRight size={13} />
          </Link>
        </aside>
      </div>
      <div className="demo-callout">
        <span className="demo-spark">
          <Sparkles size={19} />
        </span>
        <div>
          <strong>
            {app.health?.mode === 'transport'
              ? 'Start with a local audio check.'
              : 'Explore the conversation before connecting your services.'}
          </strong>
          <p>
            {app.health?.mode === 'transport'
              ? 'Join from two browser profiles, use headphones and test one microphone at a time. Speech APIs are disabled.'
              : 'The demo uses clearly labelled, scripted examples. It does not perform live translation.'}
          </p>
        </div>
        <button className="text-link" onClick={() => void start()}>
          {app.health?.mode === 'transport' ? 'Start audio check' : 'Try the workspace'}
          <ArrowRight size={16} />
        </button>
      </div>
      {join && (
        <Modal title="Join a conversation" onClose={() => setJoin(false)}>
          <p className="muted">Paste the invitation link or room code shared with you.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              joinCode(code);
            }}
          >
            <label className="field">
              <span>Invitation link or room code</span>
              <input
                autoFocus
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="e.g. demo-a1b2c3d4"
                required
              />
            </label>
            <ErrorNotice message={error} />
            <button className="button primary full" type="submit">
              Continue
              <ArrowRight size={17} />
            </button>
          </form>
        </Modal>
      )}
      <div className="sr-only">
        <label htmlFor="room-title">New conversation title</label>
        <input id="room-title" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
    </>
  );
}
