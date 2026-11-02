import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  AudioLines,
  Bookmark,
  Check,
  Download,
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
export function recapText(recap: Recap, language: Language): string {
  return `${recap.room.title}\n${recap.localDemo || recap.room.mode === 'demo' ? 'SCRIPTED DEMONSTRATION — example content\n' : ''}Ended: ${new Date(recap.ended_at).toLocaleString()}\nListening language: ${languageName(language)}\n\n${recap.turns.map((t) => `${t.speaker_name} (${languageName(t.source_language)})\nSource: ${t.text}\n${languageName(language)}: ${t.source_language === language ? t.text : t.translations[language] || '[Translation unavailable]'}\nConfirmed by: ${t.confirmed_by.length} participant(s)`).join('\n\n')}`;
}
export function RecapPage() {
  const { id } = useParams();
  const app = useApp();
  const recap = app.latestRecap?.id === id ? app.latestRecap : app.recaps.find((r) => r.id === id);
  const [language, setLanguage] = useState(app.preferences.language);
  const [toast, setToast] = useState('');
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
                  downloadText(`artha-mesh-${recap.room.code}.txt`, recapText(recap, language))
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
