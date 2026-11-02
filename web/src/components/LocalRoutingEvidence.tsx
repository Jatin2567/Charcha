import { Download, FlaskConical, Info } from 'lucide-react';
import { localRoutingReport } from '../services/localRoutingEvidence';
import { Badge, downloadJson } from './ui';
import { languageName } from '../types/domain';
import type { Language } from '../types/domain';
import './LocalRoutingEvidence.css';

const report = localRoutingReport();
const language = (code: string) => languageName(code as Language);

export function LocalRoutingEvidence() {
  return (
    <details className="panel local-routing-evidence" id="local-routing-check">
      <summary>
        <span><FlaskConical size={17} /><strong>Local routing check</strong></span>
        <Badge tone="neutral">Synthetic · first-audio only</Badge>
      </summary>
      <div className="local-routing-body">
        <div className="panel-head">
          <div>
            <h2>Five-language fixture · 30 October 2026</h2>
            <p>Saved local engineering evidence. It does not enter the live translation charts.</p>
          </div>
          <button className="button secondary" onClick={() => downloadJson('artha-local-routing-first-audio.json', localRoutingReport())}>
            <Download size={15} />Export result
          </button>
        </div>
        <div className="local-routing-counts">
          <div><strong>{report.translation_branches}</strong><span>Distinct language directions</span></div>
          <div><strong>{report.first_audible_recipient_routes}</strong><span>First-audible recipient routes</span></div>
          <div><strong>{report.synthetic_camera_receivers}</strong><span>Synthetic camera receivers</span></div>
        </div>
        <p>
          Hindi, Tamil, Bengali, Telugu and Marathi sources spoke sequentially through test doubles.
          Six local peers included a second Tamil listener. Shared translation fan-out and one
          same-language forwarding route were observed. Provider requests: <strong>0</strong>.
          Total fixture runtime: <strong>{report.wall_seconds.toFixed(3)} seconds</strong>.
        </p>
        <p className="local-routing-boundary"><Info size={17} /><span>{report.observation_boundary}</span></p>
        <p>
          Each receiver observer stopped after its first nonzero decoded audio frame. Continuous
          playback, simultaneous speech, physical microphones/cameras, listener playback and real
          Gnani/Evon translation remain unverified. Screening was off; voice cloning was not used.
        </p>
        <details className="local-routing-trials">
          <summary>Inspect the 25 individual first-audio observations</summary>
          <div className="local-routing-table">
            <table>
              <caption>One observation per source–recipient route; no p50 or p95 is inferred.</caption>
              <thead><tr><th scope="col">Source</th><th scope="col">Listener</th><th scope="col">Route</th><th scope="col">Capture → first decoded audio</th></tr></thead>
              <tbody>{report.observations.map((row) => (
                <tr key={`${row.source_language}:${row.listener_label}`}>
                  <td>{language(row.source_language)}</td>
                  <td>{row.listener_label}</td>
                  <td>{row.kind === 'same_language_forwarding' ? 'Same-language forwarding' : `Synthetic → ${language(row.target_language)}`}</td>
                  <td>{row.capture_to_first_received_pcm_ms.toLocaleString(undefined, { maximumFractionDigits: 2 })} ms</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </details>
        <p className="local-routing-warning"><strong>Shutdown warning retained.</strong> {report.shutdown_warning}</p>
        <p>
          {report.fixture_revision_note} The earlier stress failures remain in the local evidence
          archive. This corrected first-audio result does not convert those runs into passes.
        </p>
        <details className="local-routing-provenance">
          <summary>Evidence provenance and remaining checks</summary>
          <p>Original report SHA-256: <code>{report.source_report_sha256}</code></p>
          <p>
            Live five-source capacity still needs provider approval and measured admission settings.
            Real-device calls, sustained playback, semantic accuracy and microphone-to-listener
            latency have separate acceptance checks. Their measurements stay N/A until tested.
          </p>
        </details>
      </div>
    </details>
  );
}
