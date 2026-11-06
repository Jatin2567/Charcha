import { Download } from 'lucide-react';
import { Badge, downloadJson } from './ui';
import saved from '../data/publicHumanScreeningResults.json';
import { publicHumanScreeningReport } from '../services/publicSpeechScreening';
import './Preparation.css';

const languages = { hi: 'Hindi', ta: 'Tamil', bn: 'Bengali', te: 'Telugu', mr: 'Marathi' };
const ms = (value: number | null) => (value === null ? 'Not measured' : `${Math.round(value)} ms`);

export function PublicSpeechScreeningResults() {
  const report = publicHumanScreeningReport(saved);
  const ready = report && report.status !== 'not_run';
  const total = report?.baseline_by_language.reduce((sum, row) => sum + row.recordings, 0) ?? 0;
  const alarms = report?.baseline_by_language.reduce((sum, row) => sum + row.suspicious, 0) ?? 0;
  const unknown = report?.baseline_by_language.reduce((sum, row) => sum + row.unknown, 0) ?? 0;
  return (
    <section className="panel preparation-panel" aria-labelledby="public-human-screening-title">
      <div className="panel-head">
        <div>
          <h2 id="public-human-screening-title">Public human speech · local screening</h2>
          <p>
            Saved CPU screening of published human readings in five languages. This measures false
            alarms and unknown results on the selected clips; AI detection accuracy remains
            unmeasured.
          </p>
        </div>
        <Badge tone="neutral">0 provider calls</Badge>
      </div>
      {!ready ? (
        <div className="preparation-empty">
          <strong>
            {report ? 'Public-speech evaluation pending' : 'Saved result could not be validated'}
          </strong>
          <p>No human-speech measurements are available in this saved record.</p>
        </div>
      ) : (
        <>
          <p>
            {total} human recordings · {report.measured_at?.slice(0, 10)} ·{' '}
            {report.status === 'partial'
              ? 'Partial run; failures and unattempted clips retained'
              : 'Completed local pilot'}
            . The baseline uses the first 4,037.5 ms from each recording.
          </p>
          <p>
            <Badge tone="orange">Monitor mode recommended</Badge>{' '}
            {alarms} genuine clips were flagged suspicious; {unknown} were unknown. This pilot
            does not establish reliable automatic blocking. Thresholds and the live window
            remain unchanged.
          </p>
          <div className="preparation-table-wrap">
            <table>
              <caption>Full-window results · human clips only</caption>
              <thead>
                <tr>
                  <th>Language</th>
                  <th>Clips</th>
                  <th>False alarms</th>
                  <th>Other results</th>
                  <th>Classified</th>
                  <th>CPU time</th>
                </tr>
              </thead>
              <tbody>
                {report.baseline_by_language.map((row) => (
                  <tr key={row.language}>
                    <th scope="row">{languages[row.language]}</th>
                    <td>{row.recordings}</td>
                    <td>
                      {row.suspicious} / {row.recordings}
                      <small>Human clips flagged suspicious</small>
                    </td>
                    <td>
                      {row.unknown} unknown
                      <small>
                        {row.errors} failed · {row.unattempted} unattempted
                      </small>
                    </td>
                    <td>
                      {row.allow + row.suspicious} / {row.recordings}
                      <small>{row.allow} allowed; unknowns excluded</small>
                    </td>
                    <td>
                      {ms(row.compute_p50_ms)} median<small>{ms(row.compute_p95_ms)} p95</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Short-prefix sensitivity · isolated lab only</summary>
            <p>
              These experiments repeat a shorter observed prefix to fill the fixed model input.
              Repetition adds no speech evidence. Flag changes show sensitivity, not a validated
              reduction in live-call delay or preserved accuracy.
            </p>
            <div className="preparation-table-wrap">
              <table>
                <caption>Each duration uses the same source recordings</caption>
                <thead>
                  <tr>
                    <th>Observed speech</th>
                    <th>False alarms</th>
                    <th>Unknown / failed / unattempted</th>
                    <th>Flags changed from full window</th>
                  </tr>
                </thead>
                <tbody>
                  {report.prefix_summary.map((row) => (
                    <tr key={row.observed_audio_ms}>
                      <th scope="row">{row.observed_audio_ms / 1000} s</th>
                      <td>
                        {row.suspicious} / {row.recordings}
                      </td>
                      <td>
                        {row.unknown} / {row.errors} / {row.unattempted}
                      </td>
                      <td>
                        {row.verdict_changes_from_full === null
                          ? 'Not measured'
                          : `${row.verdict_changes_from_full} / ${row.paired_comparisons} paired results`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
      <p>
        CPU time excludes audio collection, network, translation and listener playback. These saved
        results are separate from live room metrics. The live screening window is unchanged.
      </p>
      <p>
        <a href="https://huggingface.co/datasets/google/fleurs" target="_blank" rel="noreferrer">
          Google FLEURS
        </a>{' '}
        is published under CC BY 4.0. Public dataset permission is distinct from consent obtained
        for this project. Speaker identities and independent-speaker count are unavailable; these
        readings do not establish performance in live meetings or on unseen AI generators.
      </p>
      <div className="preparation-footer">
        <p>
          No synthetic clips in this pilot, so AI detection rate and overall accuracy remain
          unknown. Voice cloning stays deferred.
        </p>
        {report && (
          <button
            className="button secondary"
            onClick={() => downloadJson('charcha-public-human-screening.json', report)}
          >
            <Download size={15} /> Export human-speech results
          </button>
        )}
      </div>
    </section>
  );
}
