import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download } from 'lucide-react';
import { Badge, ErrorNotice, downloadJson } from './ui';
import type { Membership } from '../types/domain';
import { fetchLocalDiagnostics } from '../services/localDiagnostics';
import { receiverProbeReport } from '../services/receiverMetrics';
import type { ReceiverProbeReport } from '../services/receiverMetrics';

const ms = (value: number | null | undefined) =>
  value == null ? 'N/A' : `${Math.round(value).toLocaleString()} ms`;

export function ReceiverAudioMetrics({ membership }: { membership: Membership | null }) {
  const [report, setReport] = useState<ReceiverProbeReport | null>(null);
  const [error, setError] = useState('');
  const [hidden, setHidden] = useState(document.hidden);
  const canRead = !!membership && !membership.localDemo && membership.room.mode !== 'demo';
  useEffect(() => {
    setReport(null);
    setError('');
    if (!membership || membership.localDemo || membership.room.mode === 'demo') return;
    let disposed = false;
    let inFlight = false;
    let controller: AbortController | null = null;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      if (disposed || document.hidden || inFlight) return;
      inFlight = true;
      controller = new AbortController();
      const request = controller;
      timeout = setTimeout(() => request.abort(), 10_000);
      try {
        const raw = await fetchLocalDiagnostics<unknown>(
          membership.room.code,
          membership.session_token,
          'audio-probes',
          request.signal,
        );
        const next = receiverProbeReport(raw, membership.participant.id);
        if (!next) throw new Error('The service returned incomplete receiver measurements.');
        if (!disposed && !request.signal.aborted) {
          setReport(next);
          setError('');
        }
      } catch {
        if (!disposed && !document.hidden)
          setError('Receiver measurements could not refresh. Displayed results may be stale.');
      } finally {
        clearTimeout(timeout);
        inFlight = false;
      }
    };
    const visibility = () => {
      setHidden(document.hidden);
      if (document.hidden) controller?.abort();
      else void poll();
    };
    document.addEventListener('visibilitychange', visibility);
    const interval = setInterval(() => void poll(), 5000);
    void poll();
    return () => {
      disposed = true;
      clearInterval(interval);
      clearTimeout(timeout);
      controller?.abort();
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [
    membership?.room.code,
    membership?.session_token,
    membership?.participant.id,
    membership?.localDemo,
    membership?.room.mode,
  ]);

  return (
    <section className="panel performance-transport" aria-labelledby="receiver-audio-title">
      <div className="panel-head">
        <div>
          <h2 id="receiver-audio-title">Receiver audio checks</h2>
          <p className="panel-intro">
            A test-tone request to decoded audio on one browser clock. This listener’s records only.
          </p>
        </div>
        <Badge tone="neutral">{hidden ? 'Refresh paused' : 'Client-reported'}</Badge>
      </div>
      <ErrorNotice message={error} />
      <div className="performance-transport-stats">
        <div>
          <span>Typical · p50</span>
          <strong>{ms(report?.summary.p50_ms)}</strong>
          <small>Request → received signal</small>
        </div>
        <div>
          <span>Tail · p95</span>
          <strong>{ms(report?.summary.p95_ms)}</strong>
          <small>Preliminary with few observations</small>
        </div>
        <div>
          <span>Detected / attempted</span>
          <strong>
            {report ? `${report.summary.detected} / ${report.summary.attempted}` : 'N/A'}
          </strong>
          <small>Failed attempts stay in the count</small>
        </div>
        <div>
          <span>Failed / cancelled</span>
          <strong>
            {report ? `${report.summary.failed} / ${report.summary.cancelled}` : 'N/A'}
          </strong>
          <small>Excluded from timing percentiles</small>
        </div>
      </div>
      <p className="performance-export-note">
        Start the tone test explicitly from the active call. This page only reads results; it never
        opens a microphone, starts a tone or requests model inference. Polling delay is included.
        These timings do not measure physical speaker output or translated speech.
      </p>
      <div className="preparation-footer">
        <p className="performance-small">
          {canRead
            ? 'Keep the call open; results refresh while this page is visible.'
            : 'Join a live or local audio room to collect receiver measurements.'}
        </p>
        {report && (
          <button
            className="button secondary"
            onClick={() => downloadJson('artha-receiver-audio-metrics.json', report)}
          >
            <Download size={14} />
            Export receiver checks
          </button>
        )}
        {!canRead && (
          <Link className="text-link" to="/">
            Start a conversation →
          </Link>
        )}
      </div>
    </section>
  );
}
