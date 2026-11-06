import { Download, Info } from 'lucide-react';
import {
  hindiTamilProviderReport,
  PROVIDER_CHAIN_COMPLETE,
} from '../services/hindiTamilProviderEvidence';
import type { ControlledProviderEvidence } from '../services/hindiTamilProviderEvidence';
import { languageName } from '../types/domain';
import { Badge, downloadJson } from './ui';
import './HindiTamilProviderEvidence.css';

const ms = (value: number | null) =>
  value === null ? 'N/A' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ms`;
const status = (value: string) =>
  value === PROVIDER_CHAIN_COMPLETE
    ? 'Protocol complete · review pending'
    : value === 'unattempted'
      ? 'Not attempted'
      : value === 'stopped_no_retry'
        ? 'Stopped · no retry'
        : value === 'cancelled'
          ? 'Cancelled'
          : 'Error';
const labels: [keyof NonNullable<ControlledProviderEvidence['used']>, string, string][] = [
  ['stt_seconds', 'STT reserved time', 'seconds'],
  ['stt_connections', 'STT connections', 'connections'],
  ['mt_requests', 'Translation requests', 'requests'],
  ['mt_characters', 'Translation source text', 'characters'],
  ['tts_requests', 'TTS requests · preparation + target', 'requests'],
  ['tts_characters', 'TTS text', 'characters'],
  ['voice_enrollments', 'Voice enrollments', 'enrollments'],
];

export function HindiTamilProviderEvidence({
  evidence = hindiTamilProviderReport(),
}: {
  evidence?: ControlledProviderEvidence | null;
}) {
  if (evidence === null) return null;
  const reference = evidence.cost_reference.local_usage_reference_inr;
  return (
    <details className="panel controlled-provider-evidence" id="controlled-provider-check">
      <summary>
        <strong>Hindi ↔ Tamil provider-chain check</strong>
        <Badge tone="neutral">Controlled stock speech · no RTC</Badge>
      </summary>
      <div className="controlled-provider-body">
        <div className="panel-head">
          <div>
            <h2>Controlled provider result · {evidence.recorded_on}</h2>
            <p>{status(evidence.status)}. Bilingual meaning review is pending.</p>
          </div>
          <button
            className="button secondary"
            onClick={() => downloadJson('charcha-hindi-tamil-provider-evidence.json', evidence)}
          >
            <Download size={15} />
            Export redacted result
          </button>
        </div>
        <p className="controlled-provider-boundary">
          <Info size={17} />
          <span>
            {evidence.boundary} One observation per direction cannot establish p50 or p95.
          </span>
        </p>
        <div className="controlled-provider-cases">
          {evidence.cases.map((row) => (
            <article key={row.case_id}>
              <header>
                <h3>
                  {languageName(row.source_language)} → {languageName(row.target_language)}
                </h3>
                <Badge tone={row.status === PROVIDER_CHAIN_COMPLETE ? 'neutral' : 'orange'}>
                  {status(row.status)}
                </Badge>
              </header>
              <div className="controlled-provider-preparation">
                <strong>Source TTS preparation · excluded from chain</strong>
                <span>
                  Complete: {ms(row.source_preparation?.complete_ms ?? null)} · First PCM:{' '}
                  {ms(row.source_preparation?.first_pcm_ms ?? null)}
                </span>
              </div>
              <dl>
                <div>
                  <dt>STT start → final transcript</dt>
                  <dd>{ms(row.stt_final_ms)}</dd>
                </div>
                <div>
                  <dt>Translation → complete text</dt>
                  <dd>{ms(row.mt_complete_ms)}</dd>
                </div>
                <div>
                  <dt>Target TTS → first PCM</dt>
                  <dd>{ms(row.target_synthesis?.first_pcm_ms ?? null)}</dd>
                </div>
                <div className="controlled-provider-chain">
                  <dt>STT start → first target PCM</dt>
                  <dd>{ms(row.stt_start_to_target_first_pcm_ms)}</dd>
                </div>
                <div>
                  <dt>STT start → complete target PCM</dt>
                  <dd>{ms(row.stt_start_to_target_complete_ms)}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
        <details className="controlled-provider-usage">
          <summary>Local usage and reference cost</summary>
          <p>{evidence.usage_boundary}</p>
          <dl>
            {labels.map(([key, label, unit]) => (
              <div key={key}>
                <dt>{label}</dt>
                <dd>
                  {evidence.used ? evidence.used[key].toLocaleString() : 'Unknown'} /{' '}
                  {evidence.caps[key].toLocaleString()} {unit}
                </dd>
              </div>
            ))}
          </dl>
          <p>
            <strong>
              STT/TTS reference for recorded units:{' '}
              {reference === null ? 'Unknown' : `₹${reference.toFixed(4)}`}
            </strong>
            . Rates: ₹27/hour STT and ₹27/10,000 TTS characters. Reviewed maximum reference: ₹2.385.
          </p>
          <p>
            Actual Gnani charge, programme-credit deduction and Modal charge:{' '}
            <strong>Unknown</strong>. These local units and reference prices are not a provider
            invoice or an account balance.
          </p>
        </details>
        <p>
          Total test wall time: {evidence.wall_seconds.toFixed(3)} seconds.{' '}
          {evidence.wall_target_exceeded ? 'The 240-second wall-time target was exceeded. ' : ''}
          Cleanup: {evidence.cleanup_complete ? 'completed' : 'incomplete; review required'}.{' '}
          {evidence.error_stage ? `Stopped at ${evidence.error_stage.replaceAll('_', ' ')}.` : ''}
        </p>
        <p>
          Source audio was deliberately generated with standard voices. This tests the provider
          protocol, not human-speech accuracy. RTC delivery, physical microphone capture, listener
          playback and semantic acceptance remain unverified. Screening is off and voice cloning is
          deferred.
        </p>
        <details className="controlled-provider-provenance">
          <summary>Evidence provenance</summary>
          <p>
            Original report SHA-256: <code>{evidence.source_report_sha256}</code>
          </p>
          <p>
            Bound plan SHA-256: <code>{evidence.plan_sha256}</code>
          </p>
        </details>
      </div>
    </details>
  );
}
