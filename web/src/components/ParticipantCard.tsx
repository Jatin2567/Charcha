import { MicOff, Mic, Hand, AudioLines } from 'lucide-react';
import { Avatar } from './ui';
import type { Participant } from '../types/domain';
import { languageName } from '../types/domain';
import type { RoomScreeningSample } from '../services/localDiagnostics';
import type { CameraTrack } from '../services/meetingVideo';
import { CameraVideo } from './CameraVideo';
import { hasVoiceFlag, screeningResultLabel } from '../services/voiceShield';
export function ParticipantCard({
  participant,
  index,
  self,
  muted,
  level,
  hand,
  stage,
  originalAudio = false,
  screening,
  videoTrack,
}: {
  participant: Participant;
  index: number;
  self: boolean;
  muted: boolean;
  level: number;
  hand: boolean;
  stage?: string;
  originalAudio?: boolean;
  screening?: RoomScreeningSample;
  videoTrack?: CameraTrack;
}) {
  const speaking = (!self || !muted) && level > 0.04;
  const signal = self ? 'Microphone' : originalAudio ? 'Original audio' : 'Translated audio';
  return (
    <article
      className={`participant-card participant-theme-${index % 4} ${speaking ? 'is-speaking' : ''} ${videoTrack ? 'has-camera' : ''}`}
    >
      <div className="participant-card-top">
        <span className="participant-language">{languageName(participant.language)}</span>
        <span className="participant-status">
          {participant.is_demo
            ? 'SAMPLE PARTICIPANT'
            : originalAudio
              ? 'ORIGINAL VOICE'
              : participant.voice_mode === 'cloned'
                ? 'PERSONAL VOICE'
                : 'STANDARD VOICE'}
        </span>
      </div>
      {!muted && screening && (
        <span
          className={`screening-card-badge ${screening.action === 'withheld' || hasVoiceFlag(screening) ? 'screening-card-review' : ''}`}
        >
          {screening.action === 'withheld'
            ? 'Audio withheld'
            : `${screeningResultLabel(screening)} · experimental`}
        </span>
      )}
      <div className="participant-portrait">
        {videoTrack ? (
          <CameraVideo track={videoTrack} self={self} name={participant.name} />
        ) : (
          <>
            <Avatar name={participant.name} large index={index} />
            {!participant.is_demo && <span className="camera-off-note">Camera off</span>}
          </>
        )}
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
              : speaking
                ? signal
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
            <span className="live-level" title={signal} aria-label={signal + ' activity'}>
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
