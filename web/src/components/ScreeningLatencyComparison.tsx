import { Download } from 'lucide-react';
import { Badge, downloadJson } from './ui';
import results from '../data/screeningLatencyResults.json';
import './Preparation.css';

const ms = (value: number) => `${Math.round(value).toLocaleString()} ms`;

export function ScreeningLatencyComparison() {
  const before = results.isolated[0];
  const after = results.isolated[1];
  const saved = before.analysis_median_ms - after.analysis_median_ms;
  return (
    <section className="panel preparation-panel" aria-labelledby="screening-latency-title">
      <div className="panel-head">
        <div>
          <h2 id="screening-latency-title">Deepfake screening · delay experiment</h2>
          <p>
            Saved CPU measurements from {results.fixture_count} synthetic diagnostics. The local
            audio launcher now uses two CPU threads, with the same model, input window and
            thresholds.
          </p>
        </div>
        <Badge tone="neutral">0 API calls</Badge>
      </div>
      <div className="preparation-grid">
        <article>
          <Badge tone="neutral">Audio evidence retained</Badge>
          <h3>{ms(results.evidence_window_ms)}</h3>
          <p>
            The model still receives all 64,600 samples. Collection takes four seconds before its
            first full-context verdict.
          </p>
        </article>
        <article>
          <Badge tone="green">Less CPU time in this test</Badge>
          <h3>
            {ms(before.analysis_median_ms)} → {ms(after.analysis_median_ms)}
          </h3>
          <p>
            {ms(saved)} saved at the median; {before.analysis_count} warm analyses per setting.
            Numerical scores and flags matched within the comparison tolerance on these diagnostics.
          </p>
        </article>
        <article>
          <Badge tone="orange">Whole-window estimate</Badge>
          <h3>
            {ms(results.evidence_window_ms + before.analysis_median_ms)} →{' '}
            {ms(results.evidence_window_ms + after.analysis_median_ms)}
          </h3>
          <p>
            About 3% lower after including collection. This adds window duration to compute; it
            excludes queueing, recognition readiness and listener playback.
          </p>
        </article>
      </div>
      <div className="preparation-table-wrap">
        <table>
          <caption>CPU thread comparison · fixed full-context input</caption>
          <thead>
            <tr>
              <th>CPU threads</th>
              <th>Isolated analysis median</th>
              <th>Two in-flight analyses median</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {results.isolated.map((entry) => (
              <tr key={entry.threads}>
                <th scope="row">
                  {entry.threads}
                  {entry.threads === 2 ? ' · local setting' : ''}
                </th>
                <td>
                  {ms(entry.analysis_median_ms)}
                  <small>
                    {ms(entry.analysis_min_ms)}–{ms(entry.analysis_max_ms)} observed
                  </small>
                </td>
                <td>
                  {results.two_inflight.find((row) => row.threads === entry.threads)
                    ? ms(
                        results.two_inflight.find((row) => row.threads === entry.threads)!
                          .analysis_median_ms,
                      )
                    : 'Not measured'}
                </td>
                <td>
                  Diagnostics only<small>Speech accuracy unverified</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Can we use less than four seconds safely?</summary>
        <p>
          We compared 0.5, 1, 2 and 3-second prefixes with the full window on five synthetic
          signals. All 20 shorter-prefix flags matched, but a model score changed by as much as{' '}
          {results.short_prefix_experiment.maximum_absolute_score_change.toFixed(3)}. These signals
          do not test genuine speech, false alarms or near-threshold decisions.
        </p>
        <p>
          Short-prefix experiments are separate lab work. Repeating a short clip to fill the model’s
          input does not add new evidence. Short scores cannot release live audio under the current
          policy. Consented genuine and generated recordings, with separate calibration and
          evaluation speakers, are needed to compare misses, false alarms and unknowns before
          considering a shorter window.
        </p>
        <p>
          Monitor mode adds no screening hold but can let audio be heard before a warning.
          Enforcement waits for the full verdict. Neither mode proves identity or liveness.
        </p>
      </details>
      <div className="preparation-footer">
        <p>
          Real-speech accuracy is unknown. These timings are saved experiments, separate from
          current room measurements. Voice cloning stays deferred.
        </p>
        <button
          className="button secondary"
          onClick={() => downloadJson('artha-screening-delay-experiment.json', results)}
        >
          <Download size={15} /> Export delay experiment
        </button>
      </div>
    </section>
  );
}
