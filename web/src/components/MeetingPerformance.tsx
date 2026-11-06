import { useMemo } from 'react';
import { usePerformance } from '../hooks/usePerformance';
import { useTransportMetrics } from '../hooks/useTransportMetrics';
import { summarize } from '../services/performance';
import type { PlaybackState } from '../services/livekit';
import type { ProbeSample } from '../services/audioProbe';
import { languageName, type Membership } from '../types/domain';
import { TurnLatencyMetrics } from './TurnLatencyMetrics';
import { ReportPersistence } from './ReportPersistence';

function milliseconds(value?: number | null) {
  return value == null ? '—' : `${Math.round(value)} ms`;
}

export function MeetingPerformance({
  membership,
  onOpenReport,
  speakerCheck,
}: {
  membership: Membership;
  onOpenReport: () => void;
  speakerCheck: {
    connected: boolean;
    playback: PlaybackState['status'];
    working: boolean;
    result: ProbeSample | null;
    run: () => void;
  };
}) {
  const { report: fetched, error } = usePerformance(membership, false, false);
  const report = fetched?.room_code === membership.room.code ? fetched : null;
  const network = useTransportMetrics(membership.room.code, membership.participant.id);
  const toneReady = speakerCheck.connected && speakerCheck.playback === 'ready';
  const tone = speakerCheck.result;
  const speech = useMemo(
    () => summarize(report?.samples.filter((sample) => sample.input_kind === 'audio') ?? []),
    [report],
  );

  return (
    <section className="side-panel-content voice-shield" aria-label="Current call measurements">
      <h3>Your connection</h3>
      <p className="source-note" role="status">
        {network ? `Updated ${new Date(network.measured_at).toLocaleTimeString()} · ${network.receiving_tracks} incoming audio tracks.`
          : speakerCheck.connected ? 'Collecting WebRTC connection statistics…' : 'Connect meeting audio to see your network measurements.'}
        {network?.receiving_tracks === 0 && ' Jitter and packet loss appear when you receive audio.'}
      </p>
      <dl className="shield-model-details">
        <div>
          <dt>Network round trip</dt>
          <dd>{milliseconds(network?.network_rtt_ms)}</dd>
        </div>
        <div>
          <dt>Audio jitter</dt>
          <dd>{milliseconds(network?.jitter_ms)}</dd>
        </div>
        <div>
          <dt>Packet loss</dt>
          <dd>
            {network?.packet_loss_percent == null
              ? '—'
              : `${network.packet_loss_percent.toFixed(1)}%`}
          </dd>
        </div>
      </dl>
      <h3>Check your speaker connection</h3>
      <p>
        Play a one-second tone just for you. This times audio reaching your browser and uses no
        speech credits.
      </p>
      <button
        type="button"
        className="button secondary full"
        disabled={!toneReady || speakerCheck.working}
        onClick={speakerCheck.run}
      >
        {speakerCheck.working ? 'Checking your connection…' : 'Play test tone'}
      </button>
      <p className="source-note" role="status">
        {!toneReady
          ? speakerCheck.connected
            ? 'Enable your speaker in the call controls to run the check.'
            : 'Connect to meeting audio to run the check.'
          : tone?.status === 'detected'
            ? `Browser detected the last tone in ${milliseconds(tone.elapsed_ms)}.`
            : tone && !speakerCheck.working
              ? 'The last check finished without a detected tone.'
              : ''}
      </p>
      <h3>Spoken translation</h3>
      <ReportPersistence status={report?.persistence} />
      {error && <p role="status">Updates paused. {error}</p>}
      {speech.live_sample_count > 0 ? (
        <>
          <p>
            Server time to first synthesized audio, across {speech.live_sample_count} completed
            language deliveries.
          </p>
          <dl className="shield-model-details">
            <div>
              <dt>Median</dt>
              <dd>{milliseconds(speech.p50_ms)}</dd>
            </div>
            <div>
              <dt>95th percentile</dt>
              <dd>{milliseconds(speech.p95_ms)}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p>
          {membership.room.mode === 'transport'
            ? 'This room carries original audio.'
            : 'Waiting for a completed spoken translation.'}
        </p>
      )}
      {speech.by_direction
        .filter((row) => row.live_sample_count || row.error_count || row.cancelled_count)
        .map((row) => (
          <p key={row.source_language + row.target_language}>
            <strong>
              {languageName(row.source_language)} → {languageName(row.target_language)}
            </strong>
            <br />
            {row.live_sample_count} completed · {row.error_count} failed · {row.cancelled_count}{' '}
            cancelled · median {milliseconds(row.p50_ms)}
          </p>
        ))}
      {report && (
        <small>
          Last report {new Date(report.generated_at).toLocaleTimeString()}. Server totals omit recognition time when it is unavailable.
        </small>
      )}
      <TurnLatencyMetrics report={report?.turn_latency} compact />
      <button className="button secondary full" onClick={onOpenReport}>
        Open detailed performance report ↗
      </button>
    </section>
  );
}
