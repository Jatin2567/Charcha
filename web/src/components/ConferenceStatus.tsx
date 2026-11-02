import { RefreshCw, Volume2, LogIn } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { ConferenceReadiness } from '../services/conferenceReadiness';
import type { PlaybackState } from '../services/livekit';
import { Badge } from './ui';
import { approvalSeconds, conferenceTitle, timeLeft } from '../services/conferencePresentation';
import { ConferenceAllowance } from './ConferenceAllowance';
import './ConferenceStatus.css';

export function ConferenceStatus({
  report,
  error,
  stale,
  mediaReady,
  muted,
  playback,
  unlocking,
  onUnlock,
  onRetry,
  onRejoin,
}: {
  report: ConferenceReadiness | null;
  error: string;
  stale: boolean;
  mediaReady: boolean;
  muted: boolean;
  playback: PlaybackState;
  unlocking: boolean;
  onUnlock: () => void;
  onRetry: () => void;
  onRejoin: () => void;
}) {
  const receivedAt = useMemo(() => performance.now(), [report]);
  const [, tick] = useState(0);
  useEffect(() => {
    if (!report?.provider_flow.expires_at) return;
    const timer = setInterval(() => tick((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [report?.provider_flow.expires_at]);
  const seconds = approvalSeconds(report, (performance.now() - receivedAt) / 1000);
  const waitingApproval =
    muted &&
    report?.provider_flow.required &&
    (report.provider_flow.status !== 'approved' || seconds === 0);
  const title = conferenceTitle(report, muted, stale, mediaReady, seconds);
  const detail = stale
    ? 'This seat is no longer active. Rejoin with your name and language; your microphone will start off.'
    : error ||
      (!mediaReady
        ? 'The camera and microphone stay off until the media connection is ready.'
        : !muted
          ? report?.mode === 'transport' || !report?.provider_flow.required
            ? 'Your original audio is shared with connected participants. You can always mute.'
            : 'Keep the microphone on until the current translated response finishes. You can always mute.'
          : report?.microphone.detail || 'Checking the room before enabling your microphone.');
  return (
    <section
      className={`conference-status ${stale ? 'conference-status-stale' : ''}`}
      data-tone={
        stale
          ? 'warning'
          : error
            ? 'danger'
            : waitingApproval || report?.microphone.reason_code === 'provider_configuration_missing'
              ? 'warning'
              : mediaReady && report?.microphone.can_unmute
                ? 'success'
                : 'neutral'
      }
      aria-label="Call readiness"
    >
      <div className="conference-status-main" role="status">
        <div>
          <strong>{title}</strong>
          <p>{detail}</p>
        </div>
        <Badge tone={stale || waitingApproval ? 'orange' : 'neutral'}>
          {stale
            ? 'Seat expired'
            : !report
              ? 'Checking room'
              : report.mode === 'transport'
                ? 'Original audio'
                : report.provider_flow.required
                  ? 'Standard-voice interpretation'
                  : 'No speech service required'}
        </Badge>
      </div>
      {!stale && report?.provider_flow.status === 'approved' && report.provider_flow.required && (
        <p className="conference-window">{timeLeft(seconds)} · No automatic renewal</p>
      )}
      <div className="conference-status-actions">
        {stale ? (
          <button onClick={onRejoin}>
            <LogIn size={14} />
            Rejoin conversation
          </button>
        ) : error || !mediaReady ? (
          <button onClick={onRetry}>
            <RefreshCw size={14} />
            Reconnect media
          </button>
        ) : null}
        {playback.status === 'blocked' && (
          <button disabled={unlocking || !mediaReady} onClick={onUnlock}>
            <Volume2 size={14} />
            {unlocking ? 'Enabling speaker…' : 'Enable speaker'}
          </button>
        )}
      </div>
      {playback.status === 'blocked' && (
        <p className="conference-playback-note">
          Your browser paused speaker playback. Enable it to hear the other participants.
        </p>
      )}
      {!stale && report && report.mode !== 'demo' && (
        <ConferenceAllowance report={report} seconds={seconds} />
      )}
    </section>
  );
}
