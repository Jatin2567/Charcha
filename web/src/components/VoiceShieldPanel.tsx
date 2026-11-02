import { useState } from 'react';
import { Download, ShieldAlert, ShieldQuestion } from 'lucide-react';
import { Badge, Modal, downloadJson } from './ui';
import type { Participant } from '../types/domain';
import type { RoomScreeningSample, RoomScreeningStatus } from '../services/localDiagnostics';
import {
  activeScreeningSamples,
  hasVoiceFlag,
  shieldingState,
  screeningMetric,
  screeningReason,
  screeningResultLabel,
} from '../services/voiceShield';
import './VoiceShieldPanel.css';

export function VoiceShieldPanel({
  samples,
  participants,
  connected,
  status,
  demo,
}: {
  samples: Record<string, RoomScreeningSample>;
  participants: Participant[];
  connected: boolean;
  status: RoomScreeningStatus | null;
  demo: boolean;
}) {
  const [reviewId, setReviewId] = useState<string | null>(null);
  const state = shieldingState(status, connected, demo);
  const observations = demo ? [] : activeScreeningSamples(samples, participants, status, connected);
  const review = observations.find(
    ({ person, sample }) => person.id === reviewId && hasVoiceFlag(sample),
  );
  const active = !demo && connected && status?.mode !== 'off' && status?.model.ready;
  const unmuted = participants.filter(
    (person) => !person.muted && !person.is_agent && !person.is_demo,
  );
  return (
    <div className="side-panel-content voice-shield">
      <div className="shield-intro">
        <span className="shield-emblem">
          <ShieldQuestion size={23} />
        </span>
        <div>
          <h3>Voice screening</h3>
          <Badge tone="neutral">Experimental model</Badge>
        </div>
      </div>
      <section
        className={`shield-example ${active ? 'shield-tone-blue' : ''}`}
        aria-label="Detector status"
      >
        <div className="shield-example-title">
          <ShieldQuestion size={19} />
          <strong>{state.label}</strong>
        </div>
        <p>{state.detail}</p>
      </section>
      <p className="shield-description">
        AASIST analyzes voice waveforms on the server CPU. Detection uses acoustic patterns in the
        original audio.
      </p>
      <dl className="shield-model-details">
        <div>
          <dt>Audio window</dt>
          <dd>{screeningMetric(status?.model.window_ms)}</dd>
        </div>
        <div>
          <dt>Decision thresholds</dt>
          <dd>
            {status?.model.ready
              ? `${screeningMetric(status.model.allow_threshold, '')} / ${screeningMetric(status.model.threshold, '')}`
              : 'Unavailable'}
          </dd>
        </div>
        <div>
          <dt>Processing</dt>
          <dd>Local CPU · zero API credits</dd>
        </div>
      </dl>
      <section aria-label="Participant voice assessments">
        <h3>Participant signals</h3>
        <p className="shield-footnote">
          Scores run from 0 to 1. Higher values indicate a stronger model spoof signal. Scores are
          uncalibrated.
        </p>
        {!connected && !demo && (
          <p className="shield-stale" role="status">
            Room updates are disconnected. Current assessments are unavailable.
          </p>
        )}
        {!observations.length && (
          <p className="shield-empty">
            {active
              ? unmuted.length
                ? 'Collecting audio. The first assessment follows a complete audio window.'
                : 'Unmute a microphone and speak for at least five seconds to receive an assessment.'
              : 'No active voice assessments.'}
          </p>
        )}
        <ul className="shield-observations">
          {observations.map(({ person, sample }) => (
            <li
              key={person.id}
              className={hasVoiceFlag(sample) ? 'shield-observation-flagged' : ''}
            >
              <strong>{person.name}</strong>
              <p className="shield-signal-label">{screeningResultLabel(sample)}</p>
              <p>{screeningReason(sample)}</p>
              <dl>
                <div>
                  <dt>Spoof score</dt>
                  <dd>{screeningMetric(sample.status === 'assessed' ? sample.score : null, '')}</dd>
                </div>
                <div>
                  <dt>Analysis time</dt>
                  <dd>{screeningMetric(sample.compute_ms)}</dd>
                </div>
                <div>
                  <dt>Queue time</dt>
                  <dd>{screeningMetric(sample.queue_ms)}</dd>
                </div>
                <div>
                  <dt>Audio window</dt>
                  <dd>{screeningMetric(sample.audio_window_ms)}</dd>
                </div>
                <div>
                  <dt>Reported action</dt>
                  <dd>{sample.action}</dd>
                </div>
              </dl>
              <small>
                Last assessed <time dateTime={sample.created_at}>{sample.created_at}</time>
              </small>
              {hasVoiceFlag(sample) && (
                <button className="button secondary full" onClick={() => setReviewId(person.id)}>
                  <ShieldAlert size={15} />
                  Review {person.name}’s signal
                </button>
              )}
            </li>
          ))}
        </ul>
        <button
          className="button secondary full"
          disabled={!observations.length}
          onClick={() =>
            downloadJson('artha-voice-screening.json', {
              record_type: 'observed_voice_screening',
              experimental: true,
              accuracy_validated: false,
              generated_at: new Date().toISOString(),
              model: status?.model,
              observations: observations.map(({ sample }) => ({ ...sample })),
            })
          }
        >
          <Download size={15} />
          Export current observations
        </button>
      </section>
      <section className="shield-validation" aria-label="Deepfake validation status">
        <h3>Validation status</h3>
        <p>
          False alarms are possible. A flag needs review, and a low score does not verify someone’s
          identity.
        </p>
        <dl>
          <div>
            <dt>Meeting accuracy</dt>
            <dd>Pending validation</dd>
          </div>
          <div>
            <dt>Physical playback impact</dt>
            <dd>Not measured</dd>
          </div>
        </dl>
        <a href="#/performance" target="_blank" rel="noreferrer" className="text-link">
          View screening measurements ↗
        </a>
        <a href="#/audio-lab" target="_blank" rel="noreferrer" className="text-link">
          Analyze a saved recording ↗
        </a>
      </section>
      {review && (
        <Modal title="Possible synthetic voice" onClose={() => setReviewId(null)}>
          <div className="shield-alert-label">
            <ShieldAlert size={16} />
            Acoustic model flag · experimental
          </div>
          <div className="shield-alert-message">
            <ShieldAlert size={26} />
            <div>
              <h3>{review.person.name}</h3>
              <p>
                The audio classifier flagged this speaker’s latest window. Verify the speaker
                through a trusted channel before relying on the conversation.
              </p>
            </div>
          </div>
          <p className="shield-alert-note">
            Observed spoof score {screeningMetric(review.sample.score, '')}. This score is
            uncalibrated and false alarms are possible.
          </p>
          <button className="button primary full" onClick={() => setReviewId(null)}>
            Return to call
          </button>
        </Modal>
      )}
    </div>
  );
}
