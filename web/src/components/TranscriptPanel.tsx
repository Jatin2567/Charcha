import { useEffect, useRef, useState } from 'react';
import { Check, CheckCheck, MessageSquareText, Send, ChevronDown, FileText } from 'lucide-react';
import { Avatar } from './ui';
import type { Language, Turn } from '../types/domain';
import { languageName } from '../types/domain';
export function TranscriptPanel({
  turns,
  language,
  selfId,
  onConfirm,
  onSubmit,
  demo,
  submitting,
}: {
  turns: Turn[];
  language: Language;
  selfId: string;
  onConfirm: (id: string) => Promise<void>;
  onSubmit: (text: string) => Promise<void>;
  demo: boolean;
  submitting: boolean;
}) {
  const [tab, setTab] = useState<'translated' | 'source'>('translated');
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState('');
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [turns.length]);
  return (
    <>
      <div className="transcript-panel-info">
        <div>
          <span className="status-dot" />
          {demo ? 'Scripted example transcript' : 'Conversation transcript'}
        </div>
        <span>{turns.length} turns</span>
      </div>
      <div className="segmented">
        <button
          className={tab === 'translated' ? 'selected' : ''}
          onClick={() => setTab('translated')}
        >
          In {languageName(language)}
        </button>
        <button className={tab === 'source' ? 'selected' : ''} onClick={() => setTab('source')}>
          Original
        </button>
      </div>
      <div
        className="transcript-feed"
        role="log"
        aria-label="Conversation transcript"
        aria-live="polite"
      >
        {!turns.length ? (
          <div className="transcript-empty">
            <span>
              <MessageSquareText size={28} strokeWidth={1.3} />
            </span>
            <h3>A space for every word.</h3>
            <p>
              {demo
                ? 'Start the scripted example to see how a conversation comes together.'
                : 'Completed speech turns will appear here when the interpretation agent is connected.'}
            </p>
            <div className="transcript-empty-note">
              <FileText size={13} />
              Review. Understand. Confirm.
            </div>
          </div>
        ) : (
          turns.map((turn, i) => {
            const confirmed = turn.confirmed_by.includes(selfId);
            const translated =
              turn.source_language === language ? turn.text : turn.translations[language];
            return (
              <article className="transcript-turn" key={turn.id}>
                <div className="transcript-turn-top">
                  <Avatar name={turn.speaker_name} index={i} />
                  <div>
                    <strong>{turn.speaker_name}</strong>
                    <small>
                      {tab === 'source'
                        ? languageName(turn.source_language)
                        : `${languageName(turn.source_language)} → ${languageName(language)}`}
                    </small>
                  </div>
                  <time>
                    {new Date(turn.created_at).toLocaleTimeString('en-IN', {
                      hour: '2-digit',
                      minute: '2-digit',
                      hour12: false,
                    })}
                  </time>
                </div>
                <p
                  className={`transcript-text ${!translated && tab === 'translated' ? 'pending-translation' : ''}`}
                >
                  {tab === 'source'
                    ? turn.text
                    : translated ||
                      (turn.status === 'processing'
                        ? 'Translation in progress…'
                        : 'Translation unavailable in this language.')}
                </p>
                {tab === 'translated' && turn.source_language !== language && (
                  <details className="transcript-original">
                    <summary>
                      Original
                      <ChevronDown size={10} />
                    </summary>
                    <p>{turn.text}</p>
                  </details>
                )}
                <button
                  className={`confirm-turn ${confirmed ? 'is-confirmed' : ''}`}
                  disabled={
                    confirmed ||
                    pending === turn.id ||
                    turn.status !== 'complete' ||
                    (tab === 'translated' && !translated)
                  }
                  onClick={() => {
                    setPending(turn.id);
                    void onConfirm(turn.id).finally(() => setPending(''));
                  }}
                >
                  {confirmed ? <CheckCheck size={12} /> : <Check size={12} />}{' '}
                  {confirmed
                    ? 'You confirmed understanding'
                    : pending === turn.id
                      ? 'Confirming…'
                      : 'Confirm understanding'}
                  {turn.confirmed_by.length > 0 && <span>{turn.confirmed_by.length}</span>}
                </button>
              </article>
            );
          })
        )}
        <div ref={bottom} />
      </div>
      <form
        className="text-composer"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim())
            void onSubmit(draft.trim())
              .then(() => setDraft(''))
              .catch(() => {});
        }}
      >
        <label htmlFor="conversation-text">
          {demo ? 'Try a scripted sentence' : 'Or send a phrase to interpret'}
        </label>
        <div>
          <input
            id="conversation-text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={2000}
            placeholder={
              demo ? 'Paste a sentence from the example' : 'Type in your speaking language…'
            }
          />
          <button
            type="submit"
            className="composer-send"
            disabled={!draft.trim() || submitting}
            aria-label="Send text for interpretation"
          >
            <Send size={16} />
          </button>
        </div>
        <small>
          {demo
            ? 'Demo text accepts only sentences in the sample script.'
            : 'Text uses your selected language and the live MT / TTS pipeline.'}
        </small>
      </form>
    </>
  );
}
