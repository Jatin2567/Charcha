import { Download } from 'lucide-react';
import type { PerformanceSample } from '../types/performance';
import { languageName } from '../types/domain';
import { latencyGroupReport } from '../services/latencyGroups';
import { Badge, downloadJson } from './ui';
import './Preparation.css';

const ms = (value: number | null) => (value === null ? 'Not measured' : `${Math.round(value)} ms`);

export function LatencyGroups({ samples }: { samples: PerformanceSample[] }) {
  const report = latencyGroupReport(samples);
  return (
    <section className="panel preparation-panel" aria-labelledby="latency-groups-title">
      <div className="panel-head">
        <div>
          <h2 id="latency-groups-title">Latency by language and input</h2>
          <p>
            Microphone and typed text have different timing boundaries. Each direction and voice
            stays separate. Current filters apply; select All outcomes to retain every failure.
          </p>
        </div>
        <Badge tone="neutral">Server timings only</Badge>
      </div>
      {report.groups.length ? (
        <div className="preparation-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Direction / input</th>
                <th>Measured / attempted</th>
                <th>Total p50 / p95</th>
                <th>Errors / cancelled</th>
              </tr>
            </thead>
            <tbody>
              {report.groups.map((group) => (
                <tr key={group.key}>
                  <th scope="row">
                    {languageName(group.source_language)} → {languageName(group.target_language)}
                    <small>
                      {group.input_kind === 'audio' ? 'Microphone' : 'Typed text'} ·{' '}
                      {group.voice_mode} voice
                    </small>
                  </th>
                  <td>
                    {group.measured} / {group.attempted}
                    <small>{group.completed_without_timing} completed without timing</small>
                    {group.partial_audio_totals > 0 && (
                      <small>
                        {group.partial_audio_totals} partial audio totals — recognition not measured
                      </small>
                    )}
                  </td>
                  <td>
                    {ms(group.total.p50_ms)} / {ms(group.total.p95_ms)}
                    <small>
                      {group.measured < 20
                        ? 'Small sample — comparison is preliminary'
                        : 'Check matching devices and network conditions'}
                    </small>
                  </td>
                  <td>
                    {group.errors} / {group.cancelled}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="preparation-empty">
          No server interpretation attempts in this selection. Local raw audio, scripted demos and
          the saved cold-start experiment cannot fill this table.
        </p>
      )}
      {report.groups.length > 0 && (
        <details>
          <summary>Inspect stage timings by direction</summary>
          <p>
            Each cell shows p50 / p95 and its measured sample count. Stage percentiles do not add up
            to the total. Cold/warm model state is not inferred from these room records.
          </p>
          <div className="preparation-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Direction / input</th>
                  <th>Queue</th>
                  <th>Recognition · STT</th>
                  <th>Translation · MT</th>
                  <th>First audio · TTS</th>
                </tr>
              </thead>
              <tbody>
                {report.groups.map((group) => (
                  <tr key={group.key}>
                    <th scope="row">
                      {languageName(group.source_language)} → {languageName(group.target_language)}
                      <small>
                        {group.input_kind === 'audio' ? 'Microphone' : 'Typed text'} ·{' '}
                        {group.voice_mode} voice
                      </small>
                    </th>
                    {[group.queue, group.recognition, group.translation, group.synthesis].map(
                      (stage, index) => (
                        <td key={index}>
                          {ms(stage.p50_ms)} / {ms(stage.p95_ms)}
                          <small>n={stage.n}</small>
                        </td>
                      ),
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <div className="preparation-footer">
        <p>
          {report.excluded_simulated} scripted and {report.excluded_forwarded} original-audio
          branches excluded. Exports include per-stage p50/p95 and counts; no transcript or audio.
        </p>
        <button
          className="button secondary"
          onClick={() => downloadJson('charcha-grouped-latency.json', report)}
        >
          <Download size={15} />
          Export grouped timings
        </button>
      </div>
    </section>
  );
}
