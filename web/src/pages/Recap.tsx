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
import { recapServerTiming } from '../services/recapTiming';
import './Recap.css';
import { recapText, whatsappRecap, printRecap } from '../services/recapExport';
import { TurnUnderstanding, TurnRecovery } from '../components/TurnUnderstanding';
import { understanding } from '../services/turnUnderstanding';

export { recapText } from '../services/recapExport';
export function RecapPage() {
  const { id } = useParams();
  const app = useApp();
  const recap = app.latestRecap?.id === id ? app.latestRecap : app.recaps.find((r) => r.id === id);
  const [language, setLanguage] = useState(app.preferences.language);
  const [toast, setToast] = useState('');
  const [sessionHash, setSessionHash] = useState<string>('');
  const [copiedHash, setCopiedHash] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [exportError, setExportError] = useState('');

  useEffect(() => {
    if (!recap) return;
    let active = true;
    setSessionHash('');
    const payload = JSON.stringify([recap.room.code, recap.room.title, recap.ended_at, recap.turns]);
    const enc = new TextEncoder();
    const buf = enc.encode(payload);
    if (typeof window !== 'undefined' && window.crypto && window.crypto.subtle) {
      window.crypto.subtle
        .digest('SHA-256', buf)
        .then((hashBuf) => {
          const hashArr = Array.from(new Uint8Array(hashBuf));
          if (active) setSessionHash(hashArr.map((b) => b.toString(16).padStart(2, '0')).join(''));
        })
        .catch(() => {
          if (active) setSessionHash('');
        });
    } else {
      if (active) setSessionHash('');
    }
    return () => { active = false; };
  }, [recap]);

  const extractedNumbers = useMemo(() => {
    if (!recap) return [];
    const numRegex = /\b\d+(?:[.,]\d+)*\b|[\u0966-\u096F\u09E6-\u09EF\u0BE6-\u0BEF\u0C66-\u0C6F]+/g;
    const set = new Set<string>();
    for (const t of recap.turns) {
      if (t.superseded_by) continue;
      const matches = t.text.match(numRegex);
      if (matches) {
        for (const m of matches) set.add(m);
      }
    }
    return Array.from(set).slice(0, 10);
  }, [recap]);

  const current = recap?.turns.filter(t => !t.superseded_by) || [];
  const confirmedTurns = current.filter(t => understanding(t).all);
  const confirmationRate =
    current.length > 0
      ? Math.round((confirmedTurns.length / current.length) * 100)
      : 0;

  const handleCopyHash = () => {
    if (!sessionHash) return;
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(sessionHash).then(() => {
        setCopiedHash(true);
        setToast('Source-record fingerprint copied to clipboard.');
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
                    <span>Shared understanding</span>
                  </div>
                  <Badge tone={confirmationRate === 100 ? 'green' : confirmationRate > 0 ? 'orange' : 'neutral'}>
                    {confirmationRate === 100 ? 'All current messages understood by listed listeners' : `${confirmationRate}% understood by all listed listeners`}
                  </Badge>
                </div>
                <p className="deal-memo-desc">
                  See who confirmed each message. Confirmation records understanding, not agreement. Earlier wording and corrections remain in the transcript.
                </p>
                <div className="deal-memo-stats">
                  <div className="deal-memo-stat">
                    <small>Shared statements</small>
                    <strong>{current.length}</strong>
                  </div>
                  <div className="deal-memo-stat highlight">
                    <small>All listed listeners confirmed</small>
                    <strong>{confirmedTurns.length} of {current.length}</strong>
                  </div>
                  <div className="deal-memo-stat">
                    <small>Languages spoken</small>
                    <strong>{[...new Set(participants.map((p) => languageName(p.language)))].join(', ') || 'None'}</strong>
                  </div>
                </div>
                {extractedNumbers.length > 0 && (
                  <div className="deal-memo-entities">
                    <div className="deal-memo-entities-head">
                      <span>Numbers mentioned</span>
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
                    {t.superseded_by ? <small>Earlier version · replaced</small> : t.replaces_id ? <small>Corrected message</small> : null}
                    <TurnRecovery turn={t} />
                    <TurnUnderstanding turn={t} participants={participants} />
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
              <button className="button primary full" onClick={() => {
                setExportError('');
                try { printRecap(recap, language, sessionHash); }
                catch (error) { setExportError((error as Error).message); }
              }}>Save PDF / Print</button>
              <button className="button secondary full" onClick={() => { setExportError(''); setShareOpen(true); }}>
                <Copy size={15} /> WhatsApp recap
              </button>
              <button
                className="button secondary full"
                onClick={() =>
                  downloadText(`charcha-${recap.room.code}.txt`, recapText(recap, language, sessionHash))
                }
              >
                <Download size={15} />
                Download transcript
              </button>
              <button
                className="button ghost full"
                onClick={() => downloadJson(`charcha-${recap.room.code}.json`, recap)}
              >
                Export JSON
              </button>
            </div>
            <p className="source-note">
              PDF opens your browser’s print dialog; choose Save as PDF. Exports include original wording and the selected translation, participant names and confirmation states. No new translation is generated. Share intentionally.
            </p>
            {exportError && <p role="alert" className="source-note">{exportError}</p>}
            <p className="source-note">The SHA-256 fingerprint identifies the source record. It does not certify accuracy or agreement.</p>
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
      {shareOpen && <Modal title="Review your WhatsApp recap" onClose={() => setShareOpen(false)}>
        <p>Original wording plus {languageName(language)}. Review names and messages before copying. Paste into WhatsApp and choose the recipient yourself.</p>
        <textarea className="recap-share-preview" aria-label="Bilingual WhatsApp recap" readOnly value={whatsappRecap(recap, language, sessionHash)} onFocus={event => event.currentTarget.select()} />
        <div className="modal-actions">
          <button className="button secondary" onClick={() => downloadText(`charcha-${recap.room.code}-whatsapp.txt`, whatsappRecap(recap, language, sessionHash))}>Download text</button>
          <button className="button primary" onClick={() => {
            setExportError('');
            if (!navigator.clipboard) { setExportError('Select the text above and copy it manually, or download the text file.'); return; }
            void navigator.clipboard.writeText(whatsappRecap(recap, language, sessionHash)).then(() => setToast('Recap copied. Paste it into WhatsApp when you are ready.')).catch(() => setExportError('Clipboard access was blocked. Select the text above and copy it manually.'));
          }}>Copy for WhatsApp</button>
        </div>
        {exportError && <p role="alert">{exportError}</p>}
      </Modal>}
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
