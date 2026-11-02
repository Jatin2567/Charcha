import { useMemo, useState } from 'react';
import { Download, Info } from 'lucide-react';
import captureGuide from '../../../docs/SPEECH_END_LATENCY.md?raw';
import { speechEndLatencyReport, summarizeSpeechEnd } from '../services/speechEndLatencyEvidence';
import type { SpeechEndCondition, SpeechEndEvidence } from '../services/speechEndLatencyEvidence';
import { Badge, downloadJson, downloadText } from './ui';
import './SpeechEndLatencyEvidence.css';

const ms = (value: number | null | undefined) =>
  value == null ? 'N/A' : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ms`;
export function SpeechEndLatencyEvidence({
  evidence = speechEndLatencyReport(),
  idPrefix = 'speech-end',
}: {
  evidence?: SpeechEndEvidence | null;
  idPrefix?: string;
}) {
  const [condition, setCondition] = useState<'all' | SpeechEndCondition>('all');
  const samples = useMemo(
    () =>
      (evidence?.samples ?? []).filter((row) => condition === 'all' || row.condition === condition),
    [evidence, condition],
  );
  const summary = summarizeSpeechEnd(samples);
  return (
    <section
      className="panel speech-end-evidence"
      id={`${idPrefix}-latency`}
      aria-labelledby={`${idPrefix}-heading`}
    >
      <div className="panel-head">
        <div>
          <h2 id={`${idPrefix}-heading`}>Speech end → listener</h2>
          <p>
            Keep decoded audio, estimated rendering and physical playback as separate measurements.
          </p>
        </div>
        <Badge tone="neutral">
          {evidence ? 'Synthetic local RTC · 0 API calls' : 'Measurement preparation'}
        </Badge>
      </div>
      <div className="speech-end-goal">
        <div>
          <span>Physical playback goal</span>
          <strong>Under 2 seconds</strong>
        </div>
        <Badge tone="orange">Not verified</Badge>
        <p>
          Local decoded-audio fixtures cannot establish this goal. Physical listener output is still
          unmeasured.
        </p>
      </div>
      <ol
        className="speech-end-boundaries"
        aria-label="Timing boundaries from the end of source speech"
      >
        <li>
          <span>Reference event</span>
          <strong>Source speech ends</strong>
          <small>Last voiced source frame playout</small>
        </li>
        <li>
          <span>Decoded RTC audio · p50</span>
          <strong>{ms(summary.p50_decoded_ms)}</strong>
          <small>One local process clock · synthetic</small>
        </li>
        <li>
          <span>Render estimate</span>
          <strong>N/A</strong>
          <small>No rendering estimate is inferred</small>
        </li>
        <li>
          <span>Physical listener playback</span>
          <strong>N/A</strong>
          <small>Needs one shared recorded clock</small>
        </li>
      </ol>
      <p className="speech-end-boundary-note">
        <Info size={16} />
        <span>
          Decoded RTC means audio samples reached the receiver software. It does not show when a
          speaker or headphone played them. A negative offset means output began before source
          speech ended; it is preserved, not clamped to zero.
        </span>
      </p>
      <div className="speech-end-filter">
        <label className="field">
          <span>Fixture condition</span>
          <select
            value={condition}
            onChange={(event) => setCondition(event.target.value as 'all' | SpeechEndCondition)}
          >
            <option value="all">All observations</option>
            <option value="first_route">First route</option>
            <option value="warm_route">Warm route</option>
          </select>
        </label>
        <dl>
          <div>
            <dt>Completed / attempted</dt>
            <dd>{evidence ? `${summary.completed} / ${summary.attempted}` : 'N/A'}</dd>
          </div>
          <div>
            <dt>Failed</dt>
            <dd>{evidence ? summary.failed : 'N/A'}</dd>
          </div>
          <div>
            <dt>Decoded RTC · p95</dt>
            <dd>{ms(summary.p95_decoded_ms)}</dd>
          </div>
        </dl>
      </div>
      <p className="speech-end-caption">
        First route and warm route describe this fixture. They do not label GPU/model startup. These
        small-sample percentiles describe decoded synthetic audio only.
      </p>
      <details>
        <summary>Review individual observations and limitations</summary>
        <div className="speech-end-table">
          <table>
            <caption>Source end → first decoded RTC audio; failed observations retain N/A.</caption>
            <thead>
              <tr>
                <th scope="col">Trial</th>
                <th scope="col">Condition</th>
                <th scope="col">Status</th>
                <th scope="col">Signed offset</th>
              </tr>
            </thead>
            <tbody>
              {samples.length ? (
                samples.map((row) => (
                  <tr key={row.trial_id}>
                    <td>{row.trial_id}</td>
                    <td>{row.condition === 'first_route' ? 'First route' : 'Warm route'}</td>
                    <td>{row.status}</td>
                    <td>{ms(row.source_end_to_decoded_ms)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4}>No validated observations for this selection.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <ul className="speech-end-limitations">
          {(
            evidence?.limitations ?? [
              'Awaiting the local fixture report. No latency result is implied.',
            ]
          ).map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
        {evidence && (
          <p className="speech-end-provenance">
            Source report SHA-256: <code>{evidence.source_report_sha256}</code>
          </p>
        )}
      </details>
      <details id={`${idPrefix}-physical-guide`}>
        <summary>Verify actual playback with one shared recording</summary>
        <ol className="speech-end-capture-steps">
          <li>
            Use one continuous recording clock. A phone may hear source and listener output in one
            channel, or isolated source/output paths may use two acoustic or electrical WAV
            channels.
          </li>
          <li>
            Annotate the last voiced source sample and first translated-output sample in a separate
            JSON record. In a single channel, manually distinguish both speakers and confirm no
            overlap or ambiguous crosstalk. Document capture routing and review it.
          </li>
          <li>
            Run the offline WAV/annotation analysis described in the guide. Retain input hashes and
            sample positions; separate device timestamps cannot replace a shared capture.
          </li>
          <li>
            Review meaning and device behavior separately. No microphone, camera, tone or provider
            flow starts from this page.
          </li>
        </ol>
        <button
          className="button secondary"
          onClick={() => downloadText('artha-speech-end-latency-guide.md', captureGuide)}
        >
          <Download size={15} />
          Download capture guide
        </button>
      </details>
      <div className="speech-end-export">
        <span>
          {evidence
            ? `Saved ${evidence.recorded_on} · Hindi → Tamil fixture`
            : 'No validated local timing evidence yet'}
        </span>
        <button
          className="button secondary"
          disabled={!evidence}
          onClick={() => evidence && downloadJson('artha-speech-end-local-evidence.json', evidence)}
        >
          <Download size={15} />
          Export local evidence
        </button>
      </div>
    </section>
  );
}
