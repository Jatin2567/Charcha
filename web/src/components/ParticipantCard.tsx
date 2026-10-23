import { MicOff, Mic, Hand, AudioLines } from 'lucide-react';
import { Avatar } from './ui';
import type { Participant } from '../types/domain';
import { languageName } from '../types/domain';
export function ParticipantCard({
  participant,
  index,
  self,
  muted,
  level,
  hand,
  stage,
}: {
  participant: Participant;
  index: number;
  self: boolean;
  muted: boolean;
  level: number;
  hand: boolean;
  stage?: string;
}) {
  const speaking = self && !muted && level > 0.04;
  return (
    <article
      className={`participant-card participant-theme-${index % 4} ${speaking ? 'is-speaking' : ''}`}
    >
      <div className="participant-card-top">
        <span className="participant-language">{languageName(participant.language)}</span>
        <span className="participant-status">
          {participant.is_demo
            ? 'SAMPLE PARTICIPANT'
            : participant.voice_mode === 'cloned'
              ? 'PERSONAL VOICE'
              : 'STANDARD VOICE'}
        </span>
      </div>
      <div className="participant-portrait">
        <Avatar name={participant.name} large index={index} />
        {speaking && <span className="speaking-ring" />}
      </div>
      <div className="participant-card-bottom">
        <div>
          <h3>
            {participant.name}
            {self && <span>(You)</span>}
          </h3>
          <p>
            {participant.is_demo
              ? 'Scripted example'
              : self
                ? 'Your microphone'
                : stage && stage !== 'idle'
                  ? stage
                  : 'Connected participant'}
          </p>
        </div>
        <div className="participant-indicators">
          {hand && (
            <span className="hand-indicator" aria-label="Your hand is raised">
              <Hand size={15} />
            </span>
          )}
          {speaking ? (
            <span className="live-level" aria-label="Microphone activity">
              {[0.4, 0.7, 1, 0.6].map((factor, i) => (
                <i key={i} style={{ height: Math.max(3, level * 22 * factor) }} />
              ))}
            </span>
          ) : (
            <span className="card-mic">
              {muted ? (
                <MicOff size={14} />
              ) : participant.is_demo ? (
                <AudioLines size={14} />
              ) : (
                <Mic size={14} />
              )}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
