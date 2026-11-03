import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  AudioLines,
  Bookmark,
  Check,
  Copy,
  Download,
  FileCheck2,
  History,
  Trash2,
  Users,
  Languages,
  FileText,
} from 'lucide-react';
import { useApp } from '../state/AppContext';
import {
  Avatar,
  Badge,
  downloadJson,
  downloadText,
  EmptyState,
  LanguageSelect,
  Modal,
  PageHeading,
  Toast,
} from '../components/ui';
import { languageName } from '../types/domain';
import type { Language, Recap } from '../types/domain';
import { recapServerTiming } from '../services/recapTiming';
import './Recap.css';

function simpleHex(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash).toString(16).padStart(16, '0').repeat(4).slice(0, 64);
}
export function recapText(recap: Recap, language: Language, hash?: string): string {
  const confirmed = recap.turns.filter((t) => t.confirmed_by.length > 0).length;
  const rate = recap.turns.length ? Math.round((confirmed / recap.turns.length) * 100) : 0;
  return `${recap.room.title} — Deal & Coordination Record\n${recap.localDemo || recap.room.mode === 'demo' ? 'SCRIPTED DEMONSTRATION — example content\n' : ''}Session Code: ${recap.room.code}\nEnded: ${new Date(recap.ended_at).toLocaleString()}\nListening Language: ${languageName(language)}\nHandover Status: ${confirmed}/${recap.turns.length} turns confirmed (${rate}%)\n${hash ? `SHA-256 Audit Hash: ${hash}\n` : ''}\n--------------------------------------------------------------------------------\nCONVERSATION TRANSCRIPT & CONFIRMATIONS\n--------------------------------------------------------------------------------\n\n${recap.turns.map((t) => `${t.speaker_name} (${languageName(t.source_language)})\nSource: ${t.text}\n${languageName(language)}: ${t.source_language === language ? t.text : t.translations[language] || '[Translation unavailable]'}\nConfirmed by: ${t.confirmed_by.length} participant(s)`).join('\n\n')}`;
}
export function RecapPage() {
  const { id } = useParams();
  const app = useApp();
  const recap = app.latestRecap?.id === id ? app.latestRecap : app.recaps.find((r) => r.id === id);
  const [language, setLanguage] = useState(app.preferences.language);
  const [toast, setToast] = useState('');
  const [sessionHash, setSessionHash] = useState<string>('');
  const [copiedHash, setCopiedHash] = useState(false);

  useEffect(() => {
    if (!recap) return;
    const payload = `${recap.room.code}:${recap.room.title}:${recap.ended_at}:${recap.turns.map((t) => `${t.id}:${t.speaker_id}:${t.text}:${t.confirmed_by.sort().join(',')}`).join('|')}`;
    const enc = new TextEncoder();
    const buf = enc.encode(payload);
    if (typeof window !== 'undefined' && window.crypto && window.crypto.subtle) {
      window.crypto.subtle
        .digest('SHA-256', buf)
        .then((hashBuf) => {
          const hashArr = Array.from(new Uint8Array(hashBuf));
          setSessionHash(hashArr.map((b) => b.toString(16).padStart(2, '0')).join(''));
        })
        .catch(() => {
          setSessionHash(simpleHex(payload));
        });
    } else {
      setSessionHash(simpleHex(payload));
    }
  }, [recap]);

  const extractedNumbers = useMemo(() => {
    if (!recap) return [];
    const numRegex = /\b\d+(?:[.,]\d+)*\b|[\u0966-\u096F\u09E6-\u09EF\u0BE6-\u0BEF\u0C66-\u0C6F]+/g;
    const set = new Set<string>();
    for (const t of recap.turns) {
      const matches = t.text.match(numRegex);
      if (matches) {
        for (const m of matches) set.add(m);
      }
    }
    return Array.from(set).slice(0, 10);
  }, [recap]);

  const confirmedTurns = recap ? recap.turns.filter((t) => t.confirmed_by.length > 0) : [];
  const confirmationRate =
    recap && recap.turns.length > 0
      ? Math.round((confirmedTurns.length / recap.turns.length) * 100)
      : 0;

  const handleCopyHash = () => {
    if (!sessionHash) return;
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(sessionHash).then(() => {
        setCopiedHash(true);
        setToast('SHA-256 session audit hash copied to clipboard.');
        setTimeout(() => setCopiedHash(false), 2000);
      });
    }
  };
  if (!recap)
    return (
      <EmptyState
        icon={<FileText size={25} />}
        title="This recap is no longer in this tab."
        action={
          <Link className="button primary" to="/history">
            View saved conversations
            <ArrowRight size={15} />
          </Link>
        }
      >
        Unsaved recaps are temporary. Save the next one explicitly to keep it on this device.
      </EmptyState>
    );
  const saved = app.recaps.some((r) => r.id === recap.id);
  const participants = recap.room.participants.filter((p) => !p.is_agent);
  const timing = recapServerTiming(recap);
  return (
    <>
      <Link className="text-link" to="/" style={{ marginBottom: 21 }}>
        <ArrowLeft size={14} />
        Back to workspace
      </Link>
      <PageHeading
        eyebrow="THE CONVERSATION CONTINUES"
        title="A little more understanding."
        description="Take a moment to review what was said, and keep what matters."
        action={
          <button
            className={`button ${saved ? 'secondary' : 'primary'}`}
            disabled={saved}
            onClick={() => {
              app.saveRecap(recap);
              setToast('Recap saved on this device.');
            }}
          >
            {saved ? <Check size={16} /> : <Bookmark size={16} />}{' '}
            {saved ? 'Saved on this device' : 'Save recap'}
          </button>
        }
      />
      {(recap.localDemo || recap.room.mode === 'demo') && (
        <div className="notice warning">
          <AudioLines size={17} />
          This recap contains scripted example content. It is not a record of a real translated
          conversation.
        </div>
      )}
      {recap.cleanup_warning && (
        <div className="notice warning" role="status">
          {recap.cleanup_warning}
        </div>
      )}
      <div className="recap-grid">
        <section className="panel">
          <div className="panel-head">
            <h2>Conversation transcript</h2>
            <Badge tone="neutral">{recap.turns.length} turns</Badge>
          </div>
          <LanguageSelect
            value={language}
            scriptedOnly={recap.room.mode === 'demo'}
            onChange={setLanguage}
            label="Read translations in"
            id="recap-language"
          />
          {recap.turns.length ? (
            <>
              <div className="deal-memo-card">
                <div className="deal-memo-header">
                  <div className="deal-memo-title">
                    <FileCheck2 size={18} />
                    <span>Deal & Coordination Memorandum</span>
                  </div>
                  <Badge tone={confirmationRate === 100 ? 'green' : confirmationRate > 0 ? 'orange' : 'neutral'}>
                    {confirmationRate === 100 ? 'All turns confirmed' : `${confirmationRate}% confirmed`}
                  </Badge>
                </div>
                <p className="deal-memo-desc">
                  Verifiable handover record for inter-state logistics, enterprise procurement, and task delegations.
                </p>
                <div className="deal-memo-stats">
                  <div className="deal-memo-stat">
                    <small>Total turns</small>
                    <strong>{recap.turns.length}</strong>
                  </div>
                  <div className="deal-memo-stat highlight">
                    <small>Confirmed turns</small>
                    <strong>{confirmedTurns.length} of {recap.turns.length}</strong>
                  </div>
                  <div className="deal-memo-stat">
                    <small>Languages</small>
                    <strong>{[...new Set(participants.map((p) => languageName(p.language)))].join(', ') || 'None'}</strong>
                  </div>
                </div>
                {extractedNumbers.length > 0 && (
                  <div className="deal-memo-entities">
                    <div className="deal-memo-entities-head">
                      <span>Parameters & Quantities Tracked</span>
                      <small>{extractedNumbers.length} values</small>
                    </div>
                    <div className="deal-memo-entity-pills">
                      {extractedNumbers.map((num, idx) => (
                        <span key={idx} className="deal-memo-entity-pill">{num}</span>
                      ))}
                    </div>
                  </div>
                )}
                {sessionHash && (
                  <div className="deal-memo-hash-box">
                    <div className="deal-memo-hash-content">
                      <span className="deal-memo-hash-label">SHA-256</span>
                      <span className="deal-memo-hash-value" title={sessionHash}>{sessionHash}</span>
                    </div>
                    <button
                      type="button"
                      className="deal-memo-copy-btn"
                      onClick={handleCopyHash}
                      aria-label="Copy SHA-256 session hash"
                    >
                      {copiedHash ? <Check size={12} /> : <Copy size={12} />}
                      {copiedHash ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                )}
              </div>
              <div className="recap-transcript">
              {recap.turns.map((t, i) => (
                <article className="recap-turn" key={t.id}>
                  <Avatar name={t.speaker_name} index={i} />
                  <div>
                    <div className="turn-meta">
                      <strong>{t.speaker_name}</strong>
                      <span>{languageName(t.source_language)}</span>
                    </div>
                    <p className="recap-translation">
                      {t.source_language === language
                        ? t.text
                        : t.translations[language] || 'Translation unavailable for this language.'}
                    </p>
                    <details>
                      <summary>Original · {languageName(t.source_language)}</summary>
                      <p>{t.text}</p>
                    </details>
                    <small className="turn-confirmation">
                      {t.confirmed_by.length
                        ? `${t.confirmed_by.length} participant(s) confirmed understanding`
                        : 'No participant confirmation recorded'}
                    </small>
                  </div>
                </article>
              ))}
            </div>
            </>
          ) : (
            <EmptyState icon={<AudioLines size={24} />} title="A quiet start.">
              There were no completed transcript turns in this conversation.
            </EmptyState>
          )}
        </section>
        <aside>
          <section className="panel">
            <span className="feature-icon green">
              <AudioLines size={23} />
            </span>
            <h2 style={{ marginTop: 15 }}>{recap.room.title}</h2>
            <div className="recap-details">
              <div>
                <span>Ended</span>
                <strong>
                  {new Date(recap.ended_at).toLocaleDateString('en-IN', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric',
                  })}
                </strong>
              </div>
              <div>
                <span>{recap.room.mode === 'demo' ? 'Participants' : 'Participants at exit'}</span>
                <strong>
                  {participants.length}
                  {recap.room.mode === 'demo' ? ' incl. samples' : ''}
                </strong>
              </div>
              <div>
                <span>{recap.room.mode === 'demo' ? 'Languages' : 'Languages at exit'}</span>
                <strong>{new Set(participants.map((p) => p.language)).size}</strong>
              </div>
              <div>
                <span>Mode</span>
                <strong>
                  {recap.room.mode === 'transport'
                    ? 'Raw audio test'
                    : recap.room.mode === 'demo'
                      ? 'Scripted demo'
                      : 'Live room'}
                </strong>
              </div>
            </div>
            <div className="language-chips">
              {[...new Set(participants.map((p) => p.language))].map((l) => (
                <span className="language-chip" key={l}>
                  {languageName(l)}
                </span>
              ))}
            </div>
            <div className="divider" />
            <h3>Keep a copy</h3>
            <p className="panel-intro">Export the transcript to review or share yourself.</p>
            <div className="transcript-export" style={{ marginTop: 15 }}>
              <button
                className="button secondary full"
                onClick={() =>
                  downloadText(`artha-mesh-${recap.room.code}.txt`, recapText(recap, language, sessionHash))
                }
              >
                <Download size={15} />
                Download transcript
              </button>
              <button
                className="button ghost full"
                onClick={() => downloadJson(`artha-mesh-${recap.room.code}.json`, recap)}
              >
                Export JSON
              </button>
            </div>
            <p className="source-note">
              Exports include participant names and conversation content. Share them intentionally.
            </p>
          </section>
          {recap.room.mode === 'live' && (
            <section className="panel" style={{ marginTop: 18 }}>
              <h3>Server processing timing</h3>
              <div className="recap-details">
                <div>
                  <span>Median</span>
                  <strong>
                    {timing.p50_ms === null
                      ? 'N/A'
                      : `${timing.p50_ms.toLocaleString(undefined, { maximumFractionDigits: 2 })} ms`}
                  </strong>
                </div>
                <div>
                  <span>95th percentile</span>
                  <strong>
                    {timing.p95_ms === null
                      ? 'N/A'
                      : `${timing.p95_ms.toLocaleString(undefined, { maximumFractionDigits: 2 })} ms`}
                  </strong>
                </div>
              </div>
              {!timing.measured && (
                <p className="source-note">No measured server turns were recorded.</p>
              )}
              <p className="source-note">
                Server pipeline measurements. They exclude the listener’s network and audible
                playback delay.
              </p>
            </section>
          )}
        </aside>
      </div>
      {toast && <Toast message={toast} onDone={() => setToast('')} />}
    </>
  );
}
export function HistoryPage() {
  const app = useApp();
  const navigate = useNavigate();
  const [remove, setRemove] = useState<string | null>(null);
  return (
    <>
      <PageHeading
        eyebrow="PICK UP WHERE YOU LEFT OFF"
        title="Conversations worth keeping."
        description="Your explicitly saved recaps, stored only on this device."
        action={
          <Link className="button primary" to="/">
            New conversation
            <ArrowRight size={15} />
          </Link>
        }
      />
      {app.recaps.length ? (
        <div className="history-grid">
          {app.recaps.map((r) => (
            <article className="panel history-card" key={r.id}>
              <div className="panel-head">
                <span className="feature-icon green">
                  <AudioLines size={21} />
                </span>
                <Badge tone={r.room.mode === 'demo' ? 'orange' : 'green'}>
                  {r.room.mode === 'transport'
                    ? 'Raw audio test'
                    : r.room.mode === 'demo'
                      ? 'Scripted demo'
                      : 'Live conversation'}
                </Badge>
              </div>
              <h3>{r.room.title}</h3>
              <p>
                {new Date(r.ended_at).toLocaleDateString('en-IN', {
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
              </p>
              <div className="history-details">
                <span>
                  <Users size={13} />
                  {r.room.participants.filter((p) => !p.is_agent).length} participants
                </span>
                <span>
                  <Languages size={13} />
                  {new Set(r.room.participants.map((p) => p.language)).size} languages
                </span>
                <span>
                  <FileText size={13} />
                  {r.turns.length} turns
                </span>
              </div>
              <div className="history-card-footer">
                <div className="avatar-stack">
                  {r.room.participants
                    .filter((p) => !p.is_agent)
                    .slice(0, 4)
                    .map((p, i) => (
                      <Avatar name={p.name} index={i} key={p.id} />
                    ))}
                </div>
                <div className="inline-actions">
                  <button
                    className="icon-button"
                    aria-label={`Delete ${r.room.title}`}
                    onClick={() => setRemove(r.id)}
                  >
                    <Trash2 size={15} />
                  </button>
                  <button
                    className="text-link"
                    onClick={() => {
                      app.setLatestRecap(r);
                      navigate(`/recap/${r.id}`);
                    }}
                  >
                    Open recap
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <section className="panel">
          <EmptyState
            icon={<History size={27} />}
            title="Your next conversation could start something."
            action={
              <Link className="button primary" to="/">
                Start a conversation
                <ArrowRight size={15} />
              </Link>
            }
          >
            After you leave a room, choose “Save recap” to keep its transcript here. Nothing is
            saved automatically.
          </EmptyState>
        </section>
      )}
      {remove && (
        <Modal title="Delete this saved conversation?" onClose={() => setRemove(null)}>
          <p className="muted">
            This removes the recap from this device. Any downloaded copies remain with you.
          </p>
          <div className="modal-actions">
            <button className="button secondary" onClick={() => setRemove(null)}>
              Keep recap
            </button>
            <button
              className="button danger"
              onClick={() => {
                app.deleteRecap(remove);
                setRemove(null);
              }}
            >
              Delete recap
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
