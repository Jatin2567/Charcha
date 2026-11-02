import type { ConferenceReadiness } from '../services/conferenceReadiness';
import { approvalLabel, timeLeft } from '../services/conferencePresentation';

const units = [
  ['stt_seconds', 'Recognition audio', 'seconds'],
  ['stt_connections', 'Recognition connections', 'connections'],
  ['mt_requests', 'Translation', 'requests'],
  ['mt_characters', 'Translation text', 'characters'],
  ['tts_requests', 'Speech generation', 'requests'],
  ['tts_characters', 'Generated speech text', 'characters'],
] as const;

export function ConferenceAllowance({
  report,
  seconds,
}: {
  report: ConferenceReadiness;
  seconds: number | null;
}) {
  return (
    <details className="conference-allowance">
      <summary>Call setup &amp; approved allowance</summary>
      <dl className="conference-setup-grid">
        <div>
          <dt>Room media</dt>
          <dd>
            {report.media.interpreter_connected && report.media.member_connected
              ? 'Connected'
              : 'Connecting'}
          </dd>
        </div>
        <div>
          <dt>Speech configuration</dt>
          <dd>
            {report.mode === 'transport'
              ? 'Disabled in original-audio mode'
              : report.providers.configured
                ? 'Present'
                : 'Incomplete'}
          </dd>
        </div>
        {report.mode === 'live' && (
          <>
            <div>
              <dt>Model availability</dt>
              <dd>Not checked</dd>
            </div>
            <div>
              <dt>Other connected translation languages</dt>
              <dd>{report.audience.connected_translation_target_languages.length}</dd>
            </div>
          </>
        )}
      </dl>
      {report.mode === 'live' && (
        <p>
          Configuration does not confirm that Evon is running. This panel reads local room status
          only; it never wakes a model or sends a speech request.
        </p>
      )}
      {report.provider_flow.required ? (
        <>
          <p>
            <strong>Approval: {approvalLabel(report.provider_flow.status, seconds)}</strong>
            {report.provider_flow.expires_at && seconds !== 0 ? ` · ${timeLeft(seconds)}` : ''}
          </p>
          <dl className="conference-setup-grid">
            {units.map(([key, label, unit]) => (
              <div key={key}>
                <dt>{label}</dt>
                <dd>
                  {report.provider_flow.remaining[key] === null
                    ? 'Not available'
                    : `${report.provider_flow.remaining[key].toLocaleString()} ${unit}`}
                </dd>
              </div>
            ))}
          </dl>
          <p>
            Remaining amounts reflect the approved flow and daily limits. Concurrent work can use
            them; the server checks again before starting speech. They are resource units, not a
            rupee charge.
          </p>
          <h4>To start or renew interpretation</h4>
          <ol>
            <li>
              Tell the operator the languages and the number and length of turns you want to test.
            </li>
            <li>
              Review the written limits and estimated charge, then explicitly approve that flow.
            </li>
            <li>
              Wait for the room to show approval, then unmute deliberately. Expired or exhausted
              flows need a new approval.
            </li>
          </ol>
          <p>No flow is approved or renewed from this page.</p>
        </>
      ) : (
        <p>Original-audio conversation uses no speech-provider allowance.</p>
      )}
      <a href="#/usage" target="_blank" rel="noreferrer">
        Open usage &amp; limits ↗
      </a>
    </details>
  );
}
