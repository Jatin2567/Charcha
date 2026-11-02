import { Download, FlaskConical, Info, Timer } from 'lucide-react';
import evidence from '../data/coldStartResults.json';
import {
  coldStartReduction,
  coldStartReport,
  summarizeColdStarts,
} from '../services/coldStartComparison';
import type { ColdStartGroup } from '../services/coldStartComparison';
import { Badge, downloadJson } from './ui';
import './ColdStartComparison.css';

const report = coldStartReport(evidence);
const ms = (value: number | null) =>
  value === null ? 'Not measured' : `${Math.round(value).toLocaleString()} ms`;

function Result({ group, phase }: { group: ColdStartGroup; phase: 'Before' | 'After' }) {
  const stats = summarizeColdStarts(group);
  return (
    <article className="cold-start-result">
      <div>
        <span>{phase}</span>
        <Timer size={16} />
      </div>
      <h3>{group.label}</h3>
      <strong>{ms(stats.median_ms)}</strong>
      <p>Median capture → received PCM</p>
      <dl>
        <div>
          <dt>Observed range</dt>
          <dd>
            {stats.sample_count ? `${ms(stats.min_ms)} – ${ms(stats.max_ms)}` : 'Not measured'}
          </dd>
        </div>
        <div>
          <dt>Measured directions</dt>
          <dd>{stats.sample_count}</dd>
        </div>
        <div>
          <dt>Passed / attempted runs</dt>
          <dd>
            {stats.passed_runs} / {stats.run_count}
          </dd>
        </div>
        <div>
          <dt>Failed / unrecorded runs</dt>
          <dd>
            {stats.failed_runs} / {stats.unrecorded_runs}
          </dd>
        </div>
      </dl>
    </article>
  );
}

export function ColdStartComparison() {
  const before = summarizeColdStarts(report.baseline),
    after = summarizeColdStarts(report.after);
  const reduction = coldStartReduction(before.median_ms, after.median_ms);
  const rows = [
    ...report.baseline.runs.map((run) => ({ ...run, phase: 'Before' })),
    ...report.after.runs.map((run) => ({ ...run, phase: 'After' })),
    ...(report.historical?.runs ?? []).map((run) => ({ ...run, phase: 'Historical' })),
  ];
  return (
    <section className="panel cold-start-comparison" aria-labelledby="cold-start-heading">
      <div className="panel-head">
        <div>
          <div className="cold-start-eyebrow">
            <FlaskConical size={15} />
            LOCAL TEST RECORD <Badge tone="neutral">0 API calls</Badge>
          </div>
          <h2 id="cold-start-heading">Cold-start audio · before & after</h2>
          <p>
            Saved engineering results from synthetic local peers. These are separate from your
            current room’s measurements.
          </p>
        </div>
        <button
          className="button secondary"
          disabled={!rows.length}
          onClick={() => downloadJson('artha-cold-start-comparison.json', report)}
        >
          <Download size={15} />
          Export evidence
        </button>
      </div>
      <div className="cold-start-results">
        <Result group={report.baseline} phase="Before" />
        <Result group={report.after} phase="After" />
      </div>
      {reduction !== null && (
        <p className="cold-start-change">
          <strong>
            {Math.abs(reduction).toFixed(1)}% {reduction >= 0 ? 'lower' : 'higher'} observed median
          </strong>
          <span>
            Descriptive comparison of the recorded samples; not a production latency guarantee.
          </span>
        </p>
      )}
      {!!report.historical?.runs.length && <aside className="cold-start-historical">
        <h3>Prior incident · excluded from comparison</h3>
        <p>{report.historical.label}. Recorded under different host load; these values do not enter either median or the percentage comparison above.</p>
        <ul>{report.historical.runs.flatMap((run, runIndex) => run.directions.map((direction, index) => <li key={`${runIndex}-${index}`}><span>{direction.route}</span><strong>{ms(direction.capture_to_first_received_pcm_ms)}</strong></li>))}</ul>
      </aside>}
      <p className="cold-start-boundary">
        <Info size={15} />
        <span>
          {report.boundary} Small samples do not establish a reliable p95. Failed runs stay visible
          and are excluded from timing summaries.
        </span>
      </p>
      {!!report.fix_summary.length && (
        <div className="cold-start-explanation">
          <h3>What changed</h3>
          <ul>
            {report.fix_summary.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {!!rows.length && (
        <details className="cold-start-details">
          <summary>
            Every recorded run and direction <span>{rows.length} runs</span>
          </summary>
          <div className="cold-start-table">
            <table>
              <caption>First received audio, measured on one process clock</caption>
              <thead>
                <tr>
                  <th>Stage / run</th>
                  <th>Direction</th>
                  <th>First received PCM</th>
                  <th>Run outcome</th>
                </tr>
              </thead>
              <tbody>
                {rows.flatMap((run, runIndex) =>
                  (run.directions.length
                    ? run.directions
                    : [{ route: 'No direction recorded', capture_to_first_received_pcm_ms: null }]
                  ).map((direction, index) => (
                    <tr key={`${runIndex}-${index}`}>
                      <td>
                        {run.phase}
                        <small>{run.run_id}</small>
                      </td>
                      <td>{direction.route}</td>
                      <td>{ms(direction.capture_to_first_received_pcm_ms)}</td>
                      <td>
                        {run.passed === true
                          ? 'Passed'
                          : run.passed === false
                            ? 'Failed · excluded'
                            : 'Not recorded'}
                        {run.notes && <small>{run.notes}</small>}
                        {run.phase === 'Historical' && <small>Excluded from before/after summaries</small>}
                      </td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {!!report.limitations.length && (
        <div className="cold-start-explanation cold-start-limits">
          <h3>Interpret these results with care</h3>
          <ul>
            {report.limitations.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="cold-start-date">
        {report.recorded_at
          ? `Evidence recorded: ${report.recorded_at}`
          : 'Awaiting recorded comparison evidence.'}{' '}
        Viewing or exporting this record starts no test, microphone, model or server.
      </p>
    </section>
  );
}
