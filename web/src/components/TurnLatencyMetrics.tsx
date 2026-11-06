import { Download } from 'lucide-react';
import { Badge, downloadJson } from './ui';
import { percentile } from '../services/performance';
import type { PerformanceFilter, TurnLatencyReport } from '../types/performance';
import { languageName } from '../types/domain';
import './TurnLatencyMetrics.css';

const ms = (n: number | null | undefined) => n == null ? 'N/A' : `${Math.round(n).toLocaleString()} ms`;
const reasons = {
  ambiguous: 'Audio overlapped, arrived before its marker, or timing was uncertain',
  muted: 'Speaker output was muted', blocked: 'Playback was blocked or disconnected',
  timeout: 'No clear audio onset before the measurement expired',
  source_unavailable: 'Source speech end could not be matched confidently',
  unreported: 'The listener did not return a measurement', detected: 'Decoded audio observed',
};
export function TurnLatencyMetrics({ report, compact = false, direction = 'all' }: {
  report?: TurnLatencyReport; compact?: boolean; direction?: PerformanceFilter['direction'];
}) {
  const rows = (report?.samples ?? []).filter((s) => direction === 'all' || `${s.source_language}:${s.target_language}` === direction);
  const measured = rows.filter((s) => s.status === 'detected' && s.latency_ms !== null && Number.isFinite(s.latency_ms) && s.latency_ms >= 0);
  const missing = rows.length - measured.length;
  const exported = () => downloadJson('charcha-listener-latency.json', {
    measurement: 'server_ingress_energy_end_to_browser_decoded_onset_estimate', physical_playback_measured: false,
    boundary: 'Energy-estimated speech end at the server to browser decoded audio; excludes microphone uplink and speaker hardware.',
    samples: rows.map((s) => ({ utterance_id: s.utterance_id, source_language: s.source_language,
      target_language: s.target_language, status: s.status, source_end_status: s.source_end_status,
      latency_ms: s.latency_ms, uncertainty_ms: s.uncertainty_ms, created_at: s.created_at })),
  });
  return <section className={compact ? 'listener-latency listener-latency-compact' : 'listener-latency panel performance-transport'} id={compact ? undefined : 'listener-latency'} aria-label="Automatic listener latency">
    <div className="panel-head"><div><h3>Speech end → received audio</h3>
      <p className="panel-intro">Automatic estimate for this listener, with measured clock uncertainty.</p></div>
      {!compact && <Badge tone="neutral">Browser observation</Badge>}
    </div>
    <div className="latency-values">
      <div><span>Typical · p50</span><strong>{ms(percentile(measured.map((s) => s.latency_ms), .5))}</strong></div>
      <div><span>Tail · p95</span><strong>{ms(percentile(measured.map((s) => s.latency_ms), .95))}</strong></div>
      <div><span>Measured / attempted</span><strong>{measured.length} / {rows.length}</strong></div>
      {!compact && <div><span>Typical timing uncertainty</span><strong>{measured.length ? `± ${ms(percentile(measured.map((s) => s.uncertainty_ms), .5))}` : 'N/A'}</strong></div>}
    </div>
    <p className="source-note">Starts at an energy-based speech-end estimate on the server; ends when decoded audio is detected with browser playback enabled. Microphone uplink and physical speaker output are not measured. This is not an acoustic speech-to-ear benchmark.</p>
    {!rows.length && <p className="source-note">No listener observations yet. Keep the call tab visible with speaker output enabled. Older meetings cannot gain these measurements retrospectively.</p>}
    {missing > 0 && <p className="source-note">{missing} attempts had no trustworthy interval and are excluded from percentiles.</p>}
    {!compact && rows.length > 0 && <>
      <div className="performance-table-wrap" tabIndex={0} aria-label="Scrollable listener observations"><table>
        <thead><tr><th>Direction</th><th>Latency</th><th>Uncertainty</th><th>Observation</th></tr></thead>
        <tbody>{rows.slice(-20).reverse().map((s) => <tr key={s.marker_id + s.listener_id}>
          <th scope="row">{languageName(s.source_language)} → {languageName(s.target_language)}</th>
          <td>{s.status === 'detected' ? ms(s.latency_ms) : 'N/A'}</td><td>{s.status === 'detected' ? `± ${ms(s.uncertainty_ms)}` : 'N/A'}</td>
          <td>{reasons[s.status] ?? 'Unmeasured'}</td></tr>)}</tbody></table></div>
      <button className="button secondary" onClick={exported}><Download size={14} />Export listener observations</button>
    </>}
  </section>;
}
