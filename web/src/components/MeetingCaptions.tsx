import { memo, useLayoutEffect, useRef, useState } from 'react';
import { ArrowDown, Captions } from 'lucide-react';
import { languageName } from '../types/domain';
import type { Language, Turn } from '../types/domain';
import './MeetingCaptions.css';

export const MeetingCaptions = memo(function MeetingCaptions({
  turns,
  language,
  selfId,
  demo,
  emptyMessage,
  large,
  onResize,
  announce,
}: {
  turns: Turn[];
  language: Language;
  selfId: string;
  demo: boolean;
  emptyMessage: string;
  large: boolean;
  onResize: () => void;
  announce: boolean;
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
                </div>
                <p dir="auto" lang={translated ? language : turn.source_language}>
                  {translated || turn.text}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
});
