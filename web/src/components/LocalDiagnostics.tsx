import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, Info, ShieldQuestion, Timer } from 'lucide-react';
import { Badge, ErrorNotice, downloadJson } from './ui';
import type { Membership } from '../types/domain';
import type { ProbeSnapshot } from '../services/audioProbe';
import { fetchLocalDiagnostics, localDiagnosticsReport, screeningSummary } from '../services/localDiagnostics';
import type { RoomScreeningSnapshot } from '../services/localDiagnostics';
import './LocalDiagnostics.css';

const ms = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? 'Not measured' : `${Math.round(value).toLocaleString()} ms`;
const policy = (mode: RoomScreeningSnapshot['mode']) => mode === 'monitor' ? 'Monitor · report only' : mode === 'enforce' ? 'Enforce · audio held for a verdict' : 'Screening off';

function useLocalDiagnostics(membership: Membership | null, includeProbes: boolean) {
  const [screening, setScreening] = useState<RoomScreeningSnapshot | null>(null);
  const [probes, setProbes] = useState<ProbeSnapshot | null>(null);
  const [error, setError] = useState('');
  const [hidden, setHidden] = useState(document.hidden);
  useEffect(() => {
    setScreening(null); setProbes(null); setError('');
    if (!membership || membership.localDemo || membership.room.mode === 'demo') return;
    const code = membership.room.code, token = membership.session_token;
    let stopped = false, inFlight = false;
    let controller: AbortController | null = null;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      if (stopped || document.hidden || inFlight) return;
      inFlight = true; controller = new AbortController();
      const current = controller;
      deadline = setTimeout(() => current.abort(), 10_000);
      try {
        const tasks = [fetchLocalDiagnostics<RoomScreeningSnapshot>(code, token, 'screening', current.signal)];
        const [screen, probe] = await Promise.all([
          tasks[0], includeProbes ? fetchLocalDiagnostics<ProbeSnapshot>(code, token, 'audio-probes', current.signal) : Promise.resolve(null),
        ]);
        if (!stopped && !current.signal.aborted) {
          if (!screen || !Array.isArray(screen.samples) || !screen.latest || !screen.model || (probe && (!Array.isArray(probe.samples) || !probe.summary)))
            throw new Error('The service returned incomplete local diagnostics.');
          setScreening(screen); setProbes(probe); setError('');
        }
      } catch (issue) {
        if (!stopped && !document.hidden) setError(issue instanceof Error && issue.name !== 'AbortError' ? issue.message : 'Local diagnostics timed out. Displayed results may be stale.');
      } finally { clearTimeout(deadline); inFlight = false; }
    };
    const visibility = () => { setHidden(document.hidden); if (document.hidden) controller?.abort(); else void poll(); };
    document.addEventListener('visibilitychange', visibility);
    const interval = setInterval(() => void poll(), includeProbes ? 5_000 : 2_000);
    void poll();
    return () => { stopped = true; clearInterval(interval); clearTimeout(deadline); controller?.abort(); document.removeEventListener('visibilitychange', visibility); };
  }, [membership?.room.code, membership?.session_token, membership?.localDemo, includeProbes]);
  return { screening, probes, error, hidden };
}

export function LocalDiagnostics({ membership }: { membership: Membership | null }) {
  const { screening, probes, error, hidden } = useLocalDiagnostics(membership, true);
  const summary = screeningSummary(screening?.samples ?? []);
  return <section className="panel local-diagnostics">
    <div className="panel-head"><div><h2>Local audio & screening measurements</h2><p>Independent measurements with their own boundaries. Refresh pauses while this tab is hidden.</p></div><button className="button secondary" disabled={!screening && !probes} onClick={() => downloadJson('artha-local-diagnostics.json', localDiagnosticsReport(probes, screening))}><Download size={15} />Export</button></div>
    <ErrorNotice message={error} />
    {!membership || membership.localDemo || membership.room.mode === 'demo' ? <p className="local-diagnostics-empty">Join a local audio room to collect these measurements. This report page never opens your microphone or starts a test.</p> : <>
      <div className="local-diagnostics-heading"><Timer size={16} /><h3>Requested tone → decoded browser audio</h3><Badge tone="neutral">{hidden ? 'Refresh paused' : 'Client-reported'}</Badge></div>
      <div className="local-diagnostics-grid"><div><span>Typical · p50</span><strong>{ms(probes?.summary.p50_ms)}</strong></div><div><span>Tail · p95</span><strong>{ms(probes?.summary.p95_ms)}</strong></div><div><span>Detected / attempted</span><strong>{probes?.summary.detected_count ?? 0} / {probes?.summary.sample_count ?? 0}</strong></div><div><span>Failed / cancelled</span><strong>{probes?.summary.failed_count ?? 0} / {probes?.summary.cancelled_count ?? 0}</strong></div></div>
      <p className="local-diagnostics-note"><Info size={14} />Run the local audio probe from the active call. One browser clock measures the request through detection of received tone energy. Polling adds delay. This is not physical speaker-output or translation latency. Small samples, particularly a single observation, do not establish a reliable p95.</p>
      <div className="local-diagnostics-heading"><ShieldQuestion size={17} /><h3>Experimental source-audio screening</h3><Badge tone="neutral">{screening ? policy(screening.mode) : 'Waiting for service'}</Badge></div>
      <div className="local-diagnostics-grid"><div><span>Compute · p50 / p95</span><strong>{ms(summary.compute_p50_ms)}</strong><small>p95 {ms(summary.compute_p95_ms)}</small></div><div><span>Estimated hold · p50</span><strong>{ms(summary.hold_p50_ms)}</strong><small>Zero in monitor mode; enforcement adds window collection</small></div><div><span>Assessed / failed windows</span><strong>{summary.assessed} / {summary.failed}</strong><small>Failed includes overload and detector errors</small></div><div><span>Spoof flags / unknown</span><strong>{summary.flagged} / {summary.unknown}</strong><small>No flag does not verify a human</small></div></div>
      <p className="local-diagnostics-note">{screening?.model.ready ? 'A local learned model is loaded. ' : 'No learned model is available. '}Scores and thresholds are experimental. Held-out Indian speech, noisy audio and unseen generators still need evaluation. Hold estimates add the audio-window duration to screening elapsed time; they exclude receiver playback. These timings are separate from the translation pipeline.</p>
      {!!screening?.samples.length && <div className="local-diagnostics-table"><table><caption>Latest screening windows</caption><thead><tr><th>Result</th><th>Action</th><th>Window</th><th>Queue</th><th>Compute</th><th>Estimated hold</th></tr></thead><tbody>{screening.samples.slice(-6).reverse().map((row, index) => <tr key={`${row.created_at}-${index}`}><td>{row.status !== 'assessed' ? `Unknown · ${row.status}` : row.verdict === 'suspicious' ? 'Spoof flag' : row.verdict === 'allow' ? 'No flag' : 'Unknown'}</td><td>{row.action}</td><td>{ms(row.audio_window_ms)}</td><td>{ms(row.queue_ms)}</td><td>{ms(row.compute_ms)}</td><td>{ms(row.hold_ms)}</td></tr>)}</tbody></table></div>}
    </>}
    <Link className="text-link" to="/audio-lab">Open Audio lab for WAV screening and shared-recording annotations →</Link>
  </section>;
}

export function RoomScreening({ membership }: { membership: Membership | null }) {
  const { screening, error } = useLocalDiagnostics(membership, false);
  if (!membership || membership.localDemo || membership.room.mode === 'demo') return null;
  const latest = Object.values(screening?.latest ?? {});
  const flags = latest.filter((sample) => sample.verdict === 'suspicious').length;
  const withheld = latest.filter((sample) => sample.action === 'withheld').length;
  const unknown = latest.filter((sample) => sample.verdict === 'unknown').length;
  return <aside className={`room-screening ${withheld || flags ? 'room-screening-warning' : ''}`} aria-live="polite">
    <ShieldQuestion size={17} />
    <div><strong>{screening ? policy(screening.mode) : 'Screening status unavailable'}</strong><p>{error ? 'Status could not refresh; displayed assessments may be stale.' : screening?.mode === 'off' ? 'Original audio is not screened.' : !latest.length ? 'Waiting for a complete audio window. No authenticity decision yet.' : `${flags} spoof flags · ${unknown} unknown · ${withheld} withheld. ${screening?.mode === 'monitor' ? 'Audio continues in monitor mode.' : 'Only low-score assessed windows are released.'}`} Experimental; no identity or liveness guarantee.</p></div>
  </aside>;
}
