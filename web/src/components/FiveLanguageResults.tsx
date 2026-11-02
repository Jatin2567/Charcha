import { Link } from 'react-router-dom';
import matrix from '../data/fiveLanguagePlan.json';
import saved from '../data/fiveLanguageStageResults.json';
import { Badge } from './ui';
import './FiveLanguageResults.css';

interface Row {
  source: string;
  target: string;
  status: string;
  stage: string | null;
  used: { stt_seconds: number; tts_characters: number; mt_requests: number };
  source_wer: number | null;
  year_review: { reference: string; recognized: string | null } | null;
  capture_start_to_receiver_first_pcm_ms: number | null;
  mt_ms: number | null;
  tts_first_pcm_ms: number | null;
}
const rows: Row[] = saved.routes;
const name = (code: string) =>
  matrix.languages.find((language) => language.code === code)?.name || code;
const seconds = (ms: number | null) => (ms == null ? '—' : (ms / 1000).toFixed(2) + ' s');
export function FiveLanguageResults() {
  const attempted = rows.filter((row) => row.status !== 'unattempted');
  const complete = attempted.filter((row) => row.status === 'receiver_decoded');
  const stt = attempted.reduce((sum, row) => sum + row.used.stt_seconds, 0);
  const chars = attempted.reduce((sum, row) => sum + row.used.tts_characters, 0);
  return (
    <section className="panel five-call-results" aria-label="Five-language call results">
      <div className="panel-head">
        <div>
          <h2>Five-language call results</h2>
          <p>
            Recorded human speech through the conference server to a second local WebRTC
            participant.
          </p>
        </div>
        <Badge tone="neutral">Standard voices</Badge>
      </div>
      {saved.recorded ? (
        <>
          <p>
            <strong>
              {complete.length} of {attempted.length} attempted routes delivered audio.
            </strong>{' '}
            The batch covers up to ten of the twenty possible directions. Physical playback and
            fluent listener review are pending.
          </p>
          <div className="five-call-table" tabIndex={0} aria-label="Scrollable route measurements">
            <table>
              <thead>
                <tr>
                  {[
                    'Direction',
                    'Receiver',
                    'Capture to first audio',
                    'Translation',
                    'Synthesis start¹',
                    'Source WER',
                  ].map((h) => (
                    <th key={h} scope="col">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.source + row.target}>
                    <th scope="row">
                      {name(row.source)} → {name(row.target)}
                    </th>
                    <td>
                      {row.status === 'receiver_decoded'
                        ? 'Audio received'
                        : row.status === 'failed'
                          ? 'Failed · ' + row.stage
                          : 'Unattempted'}
                      {row.year_review && (
                        <small className="five-call-year">
                          {row.year_review.recognized
                            ? `STT year mismatch · ${row.year_review.reference} → ${row.year_review.recognized}`
                            : `Review source year · ${row.year_review.reference}`}
                        </small>
                      )}
                    </td>
                    <td>{seconds(row.capture_start_to_receiver_first_pcm_ms)}</td>
                    <td>{seconds(row.mt_ms)}</td>
                    <td>{seconds(row.tts_first_pcm_ms)}</td>
                    <td>
                      {row.source_wer == null ? '—' : (100 * row.source_wer).toFixed(1) + '%'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            Capture time includes sending the source clip. ¹Synthesis includes output setup until
            first server PCM. Source word error rate compares the first final transcript with the
            complete reference reading. Spelling, number formatting and an early segment boundary
            affect it.
          </p>
          <p>
            <strong>Recorded usage</strong> · {stt} STT seconds ·{' '}
            {attempted.reduce((sum, r) => sum + r.used.mt_requests, 0)} translations · {chars} TTS
            characters · ₹{((stt * 27) / 3600 + (chars * 27) / 10000).toFixed(4)} Gnani reference.
            Actual invoice unverified.
          </p>
          <p>
            Modal stopped after the batch. Workspace meter change{' '}
            {saved.workspace_meter_change_usd == null
              ? 'unavailable'
              : '$' + Number(saved.workspace_meter_change_usd).toFixed(4)}
            . Billing updates can lag.
          </p>
        </>
      ) : (
        <p>Awaiting the closed batch report. No live test runs from this page.</p>
      )}
      <Link to="/tests?stage=five-language">Open the 20-direction listener checklist</Link>
      <details>
        <summary>Separate five-speaker transport test</summary>
        <p>
          Five synthetic speakers published together for three seconds. Six isolated local peers
          decoded all 25 expected recipient routes across 20 translated language branches. The first
          single-process stress check timed out. Both runs used provider doubles. Simultaneous
          live-provider capacity and physical playback still need a device test.
        </p>
      </details>
    </section>
  );
}
