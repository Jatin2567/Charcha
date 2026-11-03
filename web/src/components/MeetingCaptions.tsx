import { memo, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowDown, Captions, Check } from 'lucide-react';
import { languageName } from '../types/domain';
import type { Language, Turn } from '../types/domain';
import './MeetingCaptions.css';

const NUMBER_PATTERN = /^(\d+(?:[.,]\d+)*|[\u0966-\u096F\u09E6-\u09EF\u0BE6-\u0BEF\u0C66-\u0C6F]+)$/;
const NEGATION_PATTERN =
  /^(not|no|never|none|neither|don't|won't|can't|cannot|didn't|doesn't|isn't|aren't|नहीं|ना|मत|न|இல்லை|அல்ல|கூடாது|வேண்டாம்|లేదు|కాదు|వద్దు|नाही|नको|না|নয়|নেই)$/i;

function highlightEntities(text: string): ReactNode {
  const parts = text.split(/(\s+|[.,!?।|]+|\b)/);
  return parts.map((part, index) => {
    if (!part) return null;
    const clean = part.trim();
    if (NUMBER_PATTERN.test(clean)) {
      return (
        <mark key={index} className="entity-tag entity-number" title="Numerical quantity / parameter">
          {part}
        </mark>
      );
    }
    if (NEGATION_PATTERN.test(clean)) {
      return (
        <mark key={index} className="entity-tag entity-negation" title="Negation / exclusion condition">
          {part}
        </mark>
      );
    }
    return part;
  });
}

export const MeetingCaptions = memo(function MeetingCaptions({
  turns,
  language,
  selfId,
  demo,
  emptyMessage,
  large,
  onResize,
  announce,
  onConfirm,
}: {
  turns: Turn[];
  language: Language;
  selfId: string;
  demo: boolean;
  emptyMessage: string;
  large: boolean;
  onResize: () => void;
  announce: boolean;
  onConfirm?: (turnId: string) => void;
}) {
  const feed = useRef<HTMLDivElement>(null);
  const [following, setFollowing] = useState(true);
  useLayoutEffect(() => {
    const el = feed.current;
    if (following && el) el.scrollTop = el.scrollHeight;
  }, [turns, language, large, following]);

  return (
    <section className="meeting-captions" aria-label={demo ? 'Example captions' : 'Live captions'}>
      <div className="caption-inner">
        <header className="caption-heading">
          <h2>
            <Captions size={18} aria-hidden="true" />
            {demo ? 'Example captions' : 'Live captions'}
          </h2>
          <span className="caption-language">{languageName(language)}</span>
          <div className="caption-actions">
            {!following && (
              <button onClick={() => setFollowing(true)}>
                <ArrowDown size={14} />
                Latest
              </button>
            )}
            <button aria-pressed={large} onClick={onResize}>
              Large text
            </button>
          </div>
        </header>
        <div
          className="caption-lines"
          ref={feed}
          data-large={large}
          role="log"
          aria-label="Speaker captions"
          aria-live={announce ? 'polite' : 'off'}
          aria-relevant="additions text"
          tabIndex={turns.length ? 0 : undefined}
          onScroll={(event) => {
            const el = event.currentTarget;
            setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < 4);
          }}
        >
          {!turns.length && <p className="caption-empty">{emptyMessage}</p>}
          {turns.map((turn) => {
            const sameLanguage = turn.source_language === language;
            const translated = !sameLanguage && turn.translations[language]?.trim();
            const fallback = !sameLanguage && !translated;
            const isConfirmed = turn.confirmed_by.includes(selfId);
            return (
              <div className="caption-line" key={turn.id}>
                <div className="caption-speaker">
                  <strong>
                    {turn.speaker_name}
                    {turn.speaker_id === selfId && ' (you)'}
                  </strong>
                  <span>
                    {languageName(turn.source_language)}
                    {fallback && ' original'}
                  </span>
                  {fallback && (
                    <span className="caption-progress">
                      {turn.status === 'processing'
                        ? 'Translating…'
                        : `No ${languageName(language)} translation`}
                    </span>
                  )}
                  {turn.confirmed_by.length > 0 && (
                    <span className="caption-confirmed-badge" title="Participants who confirmed understanding">
                      <Check size={12} aria-hidden="true" />
                      {turn.confirmed_by.length} confirmed
                    </span>
                  )}
                </div>
                <div className="caption-row">
                  <div className="caption-content">
                    {translated ? (
                      <div className="caption-dual">
                        <p
                          dir="auto"
                          lang={language}
                          className="caption-translated"
                          aria-label={translated}
                          data-text={translated}
                        >
                          {highlightEntities(translated)}
                        </p>
                        <p
                          dir="auto"
                          lang={turn.source_language}
                          className="caption-original"
                          aria-label={turn.text}
                          data-text={turn.text}
                        >
                          <span className="caption-tag-pill">Original ({languageName(turn.source_language)})</span>
                          <span>{highlightEntities(turn.text)}</span>
                        </p>
                      </div>
                    ) : (
                      <p dir="auto" lang={turn.source_language} aria-label={turn.text} data-text={turn.text}>
                        {highlightEntities(turn.text)}
                      </p>
                    )}
                  </div>
                  {onConfirm && (
                    <button
                      type="button"
                      className={`caption-confirm-btn ${isConfirmed ? 'confirmed' : ''}`}
                      onClick={() => onConfirm(turn.id)}
                      disabled={isConfirmed || turn.status === 'processing'}
                      aria-label={isConfirmed ? 'You confirmed understanding' : 'Confirm understanding'}
                      title={isConfirmed ? 'Confirmed' : 'Confirm you understood this handover instruction'}
                    >
                      <Check size={13} aria-hidden="true" />
                      {isConfirmed ? 'Confirmed' : 'Confirm'}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
});
