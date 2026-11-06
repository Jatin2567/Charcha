import { Download, Info } from 'lucide-react';
import { tamilHindiFollowupReport } from '../services/tamilHindiFollowupEvidence';
import type {
  FollowupError,
  TamilHindiFollowupEvidence as Evidence,
} from '../services/tamilHindiFollowupEvidence';
import { PROVIDER_CHAIN_COMPLETE } from '../services/hindiTamilProviderEvidence';
import { Badge, downloadJson } from './ui';
import './HindiTamilProviderEvidence.css';
import './TamilHindiFollowupEvidence.css';

const ms = (value: number | null) =>
  value === null ? 'N/A' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ms`;
const errorLabels: Record<FollowupError, string> = {
  cancelled: 'Cancelled',
  timeout: 'Timeout',
  validation_error: 'Local validation error',
  provider_error: 'Provider error',
  io_error: 'Connection or local I/O error',
  unexpected_error: 'Unexpected error',
  cleanup_error: 'Cleanup error',
  flow_close_error: 'Grant close error',
};
const usageLabels: [keyof NonNullable<Evidence['used']>, string, string][] = [
  ['stt_seconds', 'STT reserved time', 'seconds'],
  ['stt_connections', 'STT connections', 'connections'],
  ['mt_requests', 'Translation requests', 'requests'],
  ['mt_characters', 'Translation source text', 'characters'],
  ['tts_requests', 'Target TTS requests', 'requests'],
  ['tts_characters', 'Target TTS text', 'characters'],
  ['voice_enrollments', 'Voice enrollments', 'enrollments'],
];
export function TamilHindiFollowupEvidence({
  evidence = tamilHindiFollowupReport(),
}: {
  evidence?: Evidence | null;
}) {
  if (evidence === null) return null;
  const complete = evidence.status === PROVIDER_CHAIN_COMPLETE;
  const reference = evidence.cost_reference.local_usage_reference_inr;
  return (
    <details
      className="panel controlled-provider-evidence tamil-hindi-followup"
      id="tamil-hindi-followup-check"
    >
      <summary>
        <strong>Tamil → Hindi follow-up</strong>
        <Badge tone="neutral">Separate controlled clip · no RTC</Badge>
      </summary>
      <div className="controlled-provider-body">
        <div className="panel-head">
          <div>
            <h2>Single follow-up result · {evidence.recorded_on}</h2>
            <p>
              {complete
                ? 'Protocol complete · meaning review pending'
                : evidence.status === 'cancelled'
                  ? 'Cancelled'
                  : 'Stopped · no retry'}
              . The original two-direction trial remains unchanged.
            </p>
          </div>
          <button
            className="button secondary"
            onClick={() => downloadJson('charcha-tamil-hindi-followup-evidence.json', evidence)}
          >
            <Download size={15} />
            Export redacted result
          </button>
        </div>
        <p>
          Reused a fixed <strong>3.2-second standard-voice Tamil clip</strong>. No source TTS
          request was made in this follow-up. This is a separate approved flow, not an automatic
          retry.
        </p>
        <dl className="followup-stt-models">
          <div>
            <dt>Requested STT model</dt>
            <dd>Prisma v3.0</dd>
          </div>
          <div>
            <dt>Provider-confirmed STT model</dt>
            <dd>Unknown</dd>
          </div>
        </dl>
        <p>
          The request selected Prisma v3.0; the saved provider response did not confirm its served
          model. A successful request alone does not establish that confirmation.
        </p>
        <p className="controlled-provider-boundary">
          <Info size={17} />
          <span>
            STT start → first target PCM includes connection setup and real-time transmission of the
            source clip, plus stream close and cleanup before translation. STT final-receipt timing
            ends before that close, so STT, MT and TTS stage values need not add up to the full chain.
            It is not speech-end delay, RTC delivery or listener playback. No duration is subtracted
            and one observation cannot establish p50 or p95.
          </span>
        </p>
        <div className="controlled-provider-cases followup-single-case">
          <article>
            <header>
              <h3>Tamil → Hindi</h3>
              <Badge tone={complete ? 'neutral' : 'orange'}>
                {complete ? 'Protocol complete · review pending' : 'Incomplete'}
              </Badge>
            </header>
            <dl>
              <div>
                <dt>STT start → final transcript</dt>
                <dd>{ms(evidence.timings.stt_final_ms)}</dd>
              </div>
              <div>
                <dt>Translation → complete text</dt>
                <dd>{ms(evidence.timings.mt_complete_ms)}</dd>
              </div>
              <div>
                <dt>Target TTS → first PCM</dt>
                <dd>{ms(evidence.timings.target_tts_first_pcm_ms)}</dd>
              </div>
              <div className="controlled-provider-chain">
                <dt>STT start → first target PCM</dt>
                <dd>{ms(evidence.timings.stt_start_to_target_first_pcm_ms)}</dd>
              </div>
              <div>
                <dt>STT start → complete target PCM</dt>
                <dd>{ms(evidence.timings.stt_start_to_target_complete_ms)}</dd>
              </div>
            </dl>
          </article>
        </div>
        {!complete && (
          <p className="followup-failure">
            <strong>Recorded failure:</strong>{' '}
            {evidence.error_class === null ? 'Unclassified' : errorLabels[evidence.error_class]}
            {evidence.error_stage ? ` at ${evidence.error_stage.replaceAll('_', ' ')}` : ''}.
            Provider message bodies and private transcript content are excluded.
          </p>
        )}
        <details className="controlled-provider-usage">
          <summary>Follow-up usage and reference cost</summary>
          <p>
            Exact local request and character reservations. STT seconds reserve connection time;
            they are not verified provider-billed speech time.
          </p>
          <dl>
            {usageLabels.map(([key, label, unit]) => (
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
              Recorded-unit STT/TTS reference:{' '}
              {reference === null ? 'Unknown' : `₹${reference.toFixed(4)}`}
            </strong>
            . Rates: ₹27/hour STT and ₹27/10,000 TTS characters; reviewed maximum reference ₹0.9975.
          </p>
          <p>
            Actual Gnani charge, programme-credit deduction and Modal charge:{' '}
            <strong>Unknown</strong>. References exclude compute, rounding and taxes and are not an
            account balance.
          </p>
        </details>
        <p>
          Test wall time: {evidence.wall_seconds.toFixed(3)} seconds. Cleanup:{' '}
          {evidence.cleanup_complete ? 'completed' : 'incomplete; review required'}. Grant:{' '}
          {evidence.flow_closed ? 'closed' : 'closure unverified'}.
        </p>
        <p>
          Human bilingual review, human-speech accuracy, physical-device calls and listener latency
          remain unverified. Screening is off and voice cloning is deferred.
        </p>
        <details className="controlled-provider-provenance">
          <summary>Fixed input and evidence provenance</summary>
          <p>
            Source report SHA-256: <code>{evidence.source_report_sha256}</code>
          </p>
          <p>
            Bound plan SHA-256: <code>{evidence.plan_sha256}</code>
          </p>
          <p>
            Fixed input SHA-256: <code>{evidence.input_sha256}</code>
          </p>
          <p>
            Translator: {evidence.translation_model}. Prompt: {evidence.prompt_version}.
          </p>
        </details>
      </div>
    </details>
  );
}
